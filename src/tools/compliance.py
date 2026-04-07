"""
Compliance Auditor Tool - Legal Reasoning Engine

Compares business privacy policy against CTDPA requirements using
semantic similarity (sentence-transformers) to identify:
  - Missing consumer rights in the policy
  - Undisclosed sensitive data processing
  - Threshold compliance issues
"""

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# Lazy-load the model (downloads ~80MB on first use)
_model = None


def _get_model() -> SentenceTransformer:
    """Lazy-load sentence transformer model."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def semantic_similarity(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two text strings."""
    model = _get_model()
    embeddings = model.encode([text_a, text_b])
    score = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return float(score)


def _split_into_paragraphs(text: str, min_length: int = 30) -> list[str]:
    """Split policy text into paragraphs for per-section comparison.

    Uses double-newlines and section headers as split points.
    Filters out very short fragments.
    """
    import re
    # Split on double-newline or section headings (numbered, lettered, or markdown)
    chunks = re.split(r"\n\s*\n|(?=\n\s*(?:\d+\.|[A-Z][.)]\s|#{1,3}\s|Section\s))", text)
    # Keep only meaningful chunks
    return [c.strip() for c in chunks if len(c.strip()) >= min_length]


# ---------- Rights compliance checking ----------

# Natural-language descriptions of each CTDPA consumer right
RIGHT_DESCRIPTIONS = {
    "access": "Consumers have the right to confirm whether their personal data is being processed and to access that personal data.",
    "correct": "Consumers have the right to correct inaccuracies in their personal data.",
    "delete": "Consumers have the right to delete personal data provided by or obtained about the consumer.",
    "portability": "Consumers have the right to obtain a copy of their personal data in a portable, readily usable format.",
    "opt-out": "Consumers have the right to opt out of the processing of personal data for targeted advertising, sale of personal data, or profiling.",
    "appeal": "Consumers have the right to appeal a controller's refusal to take action on a request within a reasonable period of time.",
}

# Keyword fallbacks: if these phrases appear in a paragraph, it very
# likely covers the right even if embedding similarity is moderate.
RIGHT_KEYWORDS = {
    "access": ["access", "request a copy", "copy of the personal data", "obtain your data", "view your data", "confirm whether"],
    "correct": ["correct", "correction", "inaccuracies", "inaccurate", "rectify", "amend"],
    "delete": ["delete", "deletion", "erase", "erasure", "remove your data", "right to delete"],
    "portability": ["portable", "portability", "machine-readable", "readily usable format", "export"],
    "opt-out": ["opt out", "opt-out", "do not sell", "targeted advertising", "profiling", "unsubscribe from processing"],
    "appeal": ["appeal", "appeal process", "appeal a refusal", "dispute", "reconsider"],
}

SIMILARITY_THRESHOLD = 0.45  # Per-paragraph threshold (much easier to meet)


def check_rights_compliance(policy_text: str, required_rights: list[str]) -> list[dict]:
    """
    Check if the business policy covers each required CTDPA consumer right.

    Splits the policy into paragraphs and compares each paragraph against
    the right description, taking the MAX similarity score. This avoids
    false positives from whole-document comparison where unrelated text
    dilutes the score.

    Also uses keyword fallback: if specific legal phrases appear in any
    paragraph, the right is considered covered even at lower similarity.
    """
    violations = []
    paragraphs = _split_into_paragraphs(policy_text)

    # Fallback: use the whole policy as one paragraph if splitting fails
    if not paragraphs:
        paragraphs = [policy_text]

    for right in required_rights:
        description = RIGHT_DESCRIPTIONS.get(right, f"right to {right}")
        keywords = RIGHT_KEYWORDS.get(right, [])

        # --- Per-paragraph similarity (take the best match) ---
        best_score = 0.0
        for para in paragraphs:
            score = semantic_similarity(para, description)
            if score > best_score:
                best_score = score

        # --- Keyword fallback ---
        policy_lower = policy_text.lower()
        keyword_found = any(kw.lower() in policy_lower for kw in keywords)

        # The right is covered if either:
        # 1. Best paragraph score >= threshold, OR
        # 2. A keyword is found AND best score >= 0.25 (loose confirmation)
        is_covered = (best_score >= SIMILARITY_THRESHOLD) or (keyword_found and best_score >= 0.25)

        if not is_covered:
            violations.append({
                "type": "MISSING_RIGHT",
                "right": right,
                "description": description,
                "similarity_score": round(best_score, 4),
                "confidence": round(1 - best_score, 4),
                "severity": "HIGH" if right in ("access", "delete", "opt-out") else "MEDIUM",
            })

    return violations


# ---------- Sensitive data disclosure checking ----------

def check_sensitive_data_disclosure(
    policy_text: str,
    pii_report: list[dict],
) -> list[dict]:
    """
    Cross-reference detected PII with the privacy policy to find
    undisclosed sensitive data processing.
    """
    violations = []
    policy_lower = policy_text.lower()

    # Map PII types to what should be disclosed in the policy
    disclosure_keywords = {
        "health_data": ["health", "medical", "diagnosis", "treatment", "health condition"],
        "biometric_data": ["biometric", "fingerprint", "facial recognition", "iris"],
        "neural_data": ["neural", "brain", "eeg", "neurofeedback"],
        "genetic_data": ["genetic", "dna", "genome"],
        "geolocation": ["geolocation", "precise location", "gps", "location data"],
        "racial_ethnic": ["race", "ethnicity", "ethnic origin", "racial"],
        "religious": ["religion", "religious", "faith"],
        "sexual_orientation": ["sexual orientation", "gender identity"],
    }

    for file_result in pii_report:
        if "error" in file_result:
            continue

        detected_types = file_result.get("pii_detected", [])

        for pii_type in detected_types:
            keywords = disclosure_keywords.get(pii_type, [])
            if keywords and not any(kw in policy_lower for kw in keywords):
                violations.append({
                    "type": "UNDISCLOSED_SENSITIVE_DATA",
                    "data_category": pii_type,
                    "source_file": file_result.get("file", "unknown"),
                    "confidence": 0.9,
                    "severity": "CRITICAL",
                    "description": f"Detected '{pii_type}' in business data but privacy policy does not disclose processing of this category.",
                })

    return violations


# ---------- Threshold compliance ----------

def check_threshold_compliance(
    threshold_rule: dict,
    pii_report: list[dict],
) -> list[dict]:
    """Check if unique consumer count triggers CTDPA applicability."""
    violations = []

    total_unique = sum(
        r.get("unique_consumers", 0) for r in pii_report if "error" not in r
    )

    threshold_value = threshold_rule.get("value")

    if threshold_value and total_unique >= threshold_value:
        violations.append({
            "type": "THRESHOLD_TRIGGERED",
            "total_unique_consumers": total_unique,
            "threshold": threshold_value,
            "confidence": threshold_rule.get("confidence", 0.8),
            "severity": "INFO",
            "description": f"Business processes data of {total_unique:,} unique consumers, exceeding the CTDPA threshold of {threshold_value:,}. Full CTDPA compliance is required.",
        })

    return violations


# ---------- Main function ----------

def check_compliance(
    business_policy: str,
    ct_rules: dict,
    pii_report: list[dict],
) -> dict:
    """
    Run full compliance audit: policy vs. CTDPA rules vs. detected PII.

    Args:
        business_policy: Full text of the business's privacy policy.
        ct_rules: Structured rules extracted by the Regulatory Analyst.
        pii_report: PII detection results from the Data Forensics agent.

    Returns:
        Compliance report with violations, status, and risk assessment.
    """
    all_violations = []

    # 1. Check consumer rights coverage
    required_rights = ct_rules.get("consumer_rights", {}).get("rights", [])
    if not required_rights:
        # Fallback to standard CTDPA rights
        required_rights = ["access", "correct", "delete", "portability", "opt-out", "appeal"]

    rights_violations = check_rights_compliance(business_policy, required_rights)
    all_violations.extend(rights_violations)

    # 2. Check sensitive data disclosure
    disclosure_violations = check_sensitive_data_disclosure(business_policy, pii_report)
    all_violations.extend(disclosure_violations)

    # 3. Check threshold compliance
    threshold_rule = ct_rules.get("threshold", {})
    threshold_violations = check_threshold_compliance(threshold_rule, pii_report)
    all_violations.extend(threshold_violations)

    # Determine overall status
    critical_count = sum(1 for v in all_violations if v.get("severity") == "CRITICAL")
    high_count = sum(1 for v in all_violations if v.get("severity") == "HIGH")

    if critical_count > 0:
        status = "Non-Compliant"
        risk_level = "CRITICAL"
    elif high_count > 0:
        status = "Non-Compliant"
        risk_level = "HIGH"
    elif all_violations:
        status = "Needs Review"
        risk_level = "MEDIUM"
    else:
        status = "Compliant"
        risk_level = "LOW"

    return {
        "violations": all_violations,
        "status": status,
        "risk_level": risk_level,
        "summary": {
            "total_violations": len(all_violations),
            "critical": critical_count,
            "high": high_count,
            "medium": sum(1 for v in all_violations if v.get("severity") == "MEDIUM"),
            "info": sum(1 for v in all_violations if v.get("severity") == "INFO"),
        },
    }
