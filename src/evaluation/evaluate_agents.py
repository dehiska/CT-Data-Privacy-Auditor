"""
Evaluation engine for the CT Data Privacy Auditor.

Computes 6 metrics from the spec:
  Tier 1 (Ragas, LLM-based):  Faithfulness, Answer Relevance, Context Precision
  Tier 2 (Custom, pure Python): Violation Accuracy, PII Precision/Recall, Policy Compliance

Usage:
    from src.evaluation.evaluate_agents import evaluate_audit
    results = evaluate_audit(report_dict, ground_truth_dict)
"""

from __future__ import annotations


# ------------------------------------------------------------------ #
# Metric 1: Violation Detection Accuracy                              #
# ------------------------------------------------------------------ #

def compute_violation_accuracy(report: dict, ground_truth: dict) -> dict:
    """Compare detected violations against expected ground truth.

    Returns accuracy, true/false positives/negatives.
    """
    # Extract detected violations from report
    violations = report.get("violations", report.get("compliance_findings", {}).get("violations", []))
    if isinstance(violations, dict):
        violations = violations.get("violations", [])

    detected = set()
    for v in violations:
        v_type = v.get("type", "")
        right = v.get("right", "")
        data_cat = v.get("data_category", "")
        key = (v_type, right or data_cat)
        detected.add(key)

    # Build expected set from ground truth
    expected = set()
    for v in ground_truth.get("expected_violations", []):
        v_type = v.get("type", "")
        right = v.get("right", "")
        data_cat = v.get("data_category", "")
        key = (v_type, right or data_cat)
        expected.add(key)

    # Build non-violation set (things that should NOT be flagged)
    non_violations = set()
    for v in ground_truth.get("expected_non_violations", []):
        v_type = v.get("type", "")
        right = v.get("right", "")
        data_cat = v.get("data_category", "")
        key = (v_type, right or data_cat)
        non_violations.add(key)

    tp = len(detected & expected)
    fp = len(detected - expected)
    fn = len(expected - detected)
    tn = len(non_violations - detected)

    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "detected": [f"{t}:{r}" for t, r in sorted(detected)],
        "expected": [f"{t}:{r}" for t, r in sorted(expected)],
    }


# ------------------------------------------------------------------ #
# Metric 2: PII Detection Precision / Recall                         #
# ------------------------------------------------------------------ #

def compute_pii_precision_recall(report: dict, ground_truth: dict) -> dict:
    """Compare detected PII types against expected ground truth.

    Returns precision, recall, F1-score.
    """
    # Extract detected PII types from report
    pii_findings = report.get("pii_detection_findings", report.get("pii_findings", {}))
    detected_types = set()

    if isinstance(pii_findings, dict):
        details = pii_findings.get("details", pii_findings.get("files", []))
        if isinstance(details, list):
            for file_result in details:
                for pii_item in file_result.get("pii_detected", []):
                    if isinstance(pii_item, dict):
                        detected_types.add(pii_item.get("type", "").lower())
                    elif isinstance(pii_item, str):
                        detected_types.add(pii_item.lower())
        # Also check top-level pii_types
        for t in pii_findings.get("pii_types", []):
            detected_types.add(t.lower() if isinstance(t, str) else "")
    elif isinstance(pii_findings, list):
        for file_result in pii_findings:
            for pii_item in file_result.get("pii_detected", []):
                if isinstance(pii_item, dict):
                    detected_types.add(pii_item.get("type", "").lower())
                elif isinstance(pii_item, str):
                    detected_types.add(pii_item.lower())

    detected_types.discard("")

    expected_types = set(t.lower() for t in ground_truth.get("expected_pii_types", []))

    tp = len(detected_types & expected_types)
    fp = len(detected_types - expected_types)
    fn = len(expected_types - detected_types)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "detected": sorted(detected_types),
        "expected": sorted(expected_types),
        "missed": sorted(expected_types - detected_types),
        "extra": sorted(detected_types - expected_types),
    }


# ------------------------------------------------------------------ #
# Metric 3: Policy Compliance Score                                   #
# ------------------------------------------------------------------ #

def compute_policy_compliance_score(report: dict, ground_truth: dict) -> dict:
    """Check if the auditor correctly identified which rights are covered.

    For each of 6 CTDPA rights, compares:
      - expected: True (policy covers it) / False (policy doesn't)
      - detected: was it flagged as MISSING_RIGHT?

    Score = correctly classified rights / total rights.
    """
    expected_coverage = ground_truth.get("expected_rights_coverage", {})
    total_clauses = ground_truth.get("total_ctdpa_clauses", 6)

    # Extract which rights were flagged as MISSING
    violations = report.get("violations", report.get("compliance_findings", {}).get("violations", []))
    if isinstance(violations, dict):
        violations = violations.get("violations", [])

    missing_rights = set()
    for v in violations:
        if v.get("type") == "MISSING_RIGHT":
            missing_rights.add(v.get("right", "").lower())

    per_right = {}
    correct = 0

    for right, is_covered in expected_coverage.items():
        detected_as_missing = right.lower() in missing_rights
        # Correct if: covered AND not flagged, OR not covered AND flagged
        is_correct = (is_covered and not detected_as_missing) or (not is_covered and detected_as_missing)
        per_right[right] = {
            "expected_covered": is_covered,
            "detected_missing": detected_as_missing,
            "correct": is_correct,
        }
        if is_correct:
            correct += 1

    score = correct / total_clauses if total_clauses > 0 else 0.0

    return {
        "score": round(score, 4),
        "correct": correct,
        "total": total_clauses,
        "per_right": per_right,
    }


# ------------------------------------------------------------------ #
# Per-Agent Breakdown                                                 #
# ------------------------------------------------------------------ #

def compute_per_agent_breakdown(
    report: dict,
    violation_result: dict | None,
    pii_result: dict | None,
    compliance_result: dict | None,
) -> dict:
    """Compute per-agent evaluation metrics."""
    agents = {}

    # Regulatory Analyst — did it extract rules?
    reg_analysis = report.get("regulatory_analysis", {})
    has_rules = bool(reg_analysis.get("consumer_rights") or reg_analysis.get("rules"))
    agents["Regulatory Analyst"] = {
        "status": "PASS" if has_rules else "PARTIAL",
        "note": "Extracted structured rules" if has_rules else "Rules extraction incomplete",
    }

    # Data Forensics — PII precision/recall
    if pii_result:
        agents["Data Forensics"] = {
            "precision": pii_result["precision"],
            "recall": pii_result["recall"],
            "f1": pii_result["f1"],
            "status": "PASS" if pii_result["f1"] >= 0.7 else "NEEDS_IMPROVEMENT",
        }
    else:
        agents["Data Forensics"] = {"status": "NOT_EVALUATED"}

    # Compliance Auditor — violation accuracy + compliance score
    if violation_result and compliance_result:
        agents["Compliance Auditor"] = {
            "violation_accuracy": violation_result["accuracy"],
            "policy_compliance_score": compliance_result["score"],
            "status": "PASS" if violation_result["accuracy"] >= 0.7 and compliance_result["score"] >= 0.7 else "NEEDS_IMPROVEMENT",
        }
    else:
        agents["Compliance Auditor"] = {"status": "NOT_EVALUATED"}

    # Appeals Processor — did it detect appeal status correctly?
    appeals = report.get("appeals_findings", report.get("appeals_analysis", {}))
    has_appeal_data = bool(appeals.get("appeal_procedure") or appeals.get("has_appeal_procedure"))
    agents["Appeals Processor"] = {
        "status": "PASS" if has_appeal_data else "PARTIAL",
        "note": "Appeal analysis completed" if has_appeal_data else "Appeal data incomplete",
    }

    # Report Generator — did it produce a structured report?
    has_exec = bool(report.get("executive_summary"))
    has_violations = bool(report.get("violations") or report.get("compliance_findings"))
    agents["Report Generator"] = {
        "has_executive_summary": has_exec,
        "has_violations": has_violations,
        "status": "PASS" if has_exec and has_violations else "PARTIAL",
    }

    return agents


# ------------------------------------------------------------------ #
# Main evaluation function                                            #
# ------------------------------------------------------------------ #

def evaluate_audit(report: dict, ground_truth: dict | None = None) -> dict:
    """Run all evaluation metrics on an audit report.

    Args:
        report: The audit report dict (from run_audit or loaded JSON).
        ground_truth: Optional ground truth dict. If None, only Ragas
                      metrics are attempted (custom metrics skipped).

    Returns:
        Dict with keys: custom_metrics, ragas_metrics, per_agent, has_ground_truth
    """
    result = {
        "custom_metrics": None,
        "ragas_metrics": None,
        "per_agent": None,
        "has_ground_truth": ground_truth is not None,
    }

    # --- Custom metrics (require ground truth) ---
    violation_result = None
    pii_result = None
    compliance_result = None

    if ground_truth:
        violation_result = compute_violation_accuracy(report, ground_truth)
        pii_result = compute_pii_precision_recall(report, ground_truth)
        compliance_result = compute_policy_compliance_score(report, ground_truth)

        result["custom_metrics"] = {
            "violation_accuracy": violation_result,
            "pii_detection": pii_result,
            "policy_compliance": compliance_result,
        }

    # --- Ragas metrics (LLM-based, optional) ---
    try:
        from src.evaluation.ragas_adapter import compute_ragas_metrics

        # Build evaluation inputs from the report
        question = "Does this business comply with the Connecticut Data Privacy Act (CTDPA)?"
        answer = _build_answer_text(report)
        contexts = _build_context_list(report)

        ragas_result = compute_ragas_metrics(question, answer, contexts)
        result["ragas_metrics"] = ragas_result
    except ImportError:
        result["ragas_metrics"] = None
    except Exception as e:
        result["ragas_metrics"] = {"error": str(e)}

    # --- Per-agent breakdown ---
    result["per_agent"] = compute_per_agent_breakdown(
        report, violation_result, pii_result, compliance_result
    )

    return result


def _build_answer_text(report: dict) -> str:
    """Build a text answer from the report for Ragas evaluation."""
    parts = []
    es = report.get("executive_summary", {})
    if es:
        parts.append(f"Compliance Status: {es.get('overall_compliance_status', 'Unknown')}")
        parts.append(f"Risk Grade: {es.get('risk_grade', '?')}")
        parts.append(f"Summary: {es.get('summary', '')}")

    violations = report.get("violations", [])
    if isinstance(violations, list):
        for v in violations:
            parts.append(f"Violation: {v.get('type', '')} - {v.get('right', '')} ({v.get('severity', '')})")

    recs = report.get("recommendations", [])
    if isinstance(recs, list):
        for r in recs:
            parts.append(f"Recommendation: {r.get('recommendation', '')}")

    return "\n".join(parts) if parts else "No structured data found in report."


def _build_context_list(report: dict) -> list[str]:
    """Build context strings from the report for Ragas evaluation."""
    contexts = []

    reg = report.get("regulatory_analysis", {})
    if reg:
        contexts.append(f"Regulatory Analysis: {str(reg)[:2000]}")

    pii = report.get("pii_detection_findings", report.get("pii_findings", {}))
    if pii:
        contexts.append(f"PII Findings: {str(pii)[:2000]}")

    appeals = report.get("appeals_findings", report.get("appeals_analysis", {}))
    if appeals:
        contexts.append(f"Appeals Findings: {str(appeals)[:2000]}")

    return contexts if contexts else ["No context available"]
