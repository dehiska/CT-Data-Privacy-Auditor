"""
Report Generator Tool - Final Audit Report Synthesizer

Compiles all findings from the pipeline into a comprehensive,
structured JSON audit report with metadata, risk scoring, and
actionable recommendations.
"""

import json
from datetime import datetime
from pathlib import Path


# ---------- Recommendation engine ----------

RECOMMENDATIONS = {
    "MISSING_RIGHT": {
        "access": "Update your privacy policy to clearly state that consumers can confirm and access their personal data. Provide a mechanism (e.g., web form, email) for submitting access requests.",
        "correct": "Add a provision allowing consumers to correct inaccuracies in their personal data. Describe the correction process.",
        "delete": "Include a clear right-to-delete provision. Specify how consumers can request deletion and any exceptions.",
        "portability": "State that consumers can obtain their personal data in a portable, readily usable format (e.g., CSV, JSON).",
        "opt-out": "Add opt-out rights for targeted advertising, sale of personal data, and profiling. Consider a universal opt-out mechanism.",
        "appeal": "Establish and document an appeal process for when consumer requests are denied.",
    },
    "UNDISCLOSED_SENSITIVE_DATA": "Update your privacy policy to explicitly disclose the processing of {data_category} data. Under CTDPA, processing sensitive data requires the consumer's consent.",
    "CRITICAL_NO_APPEAL": "Immediately establish an appeal process. CTDPA Sec. 42-520(a)(4) requires controllers to inform consumers of their right to appeal and provide an online mechanism for submitting appeals.",
    "LATE_RESPONSE": "Implement a request tracking system to ensure all consumer requests receive responses within 45 calendar days. Consider automated reminders at 30 and 40 days.",
    "EXTREME_LATE_RESPONSE": "URGENT: Responses exceeding 90 days represent serious CTDPA violations. Audit your request handling process immediately and consider additional staffing or automation.",
    "THRESHOLD_TRIGGERED": "Your organization processes data from enough consumers to trigger full CTDPA compliance requirements. Ensure all provisions are implemented.",
    "WEAK_APPEAL_PROCESS": "Strengthen your appeal process documentation. Include specific instructions, timelines, and an online submission mechanism.",
}


def generate_recommendations(violations: list[dict]) -> list[dict]:
    """Generate actionable recommendations based on identified violations."""
    recs = []

    for v in violations:
        v_type = v.get("type", "")

        if v_type == "MISSING_RIGHT":
            right = v.get("right", "")
            text = RECOMMENDATIONS.get("MISSING_RIGHT", {}).get(right, f"Add the '{right}' right to your privacy policy.")
            recs.append({
                "for_violation": v_type,
                "right": right,
                "priority": "HIGH" if right in ("access", "delete", "opt-out") else "MEDIUM",
                "recommendation": text,
            })
        elif v_type == "UNDISCLOSED_SENSITIVE_DATA":
            category = v.get("data_category", "unknown")
            text = RECOMMENDATIONS.get(v_type, "").format(data_category=category)
            recs.append({
                "for_violation": v_type,
                "data_category": category,
                "priority": "CRITICAL",
                "recommendation": text,
            })
        elif v_type in RECOMMENDATIONS:
            recs.append({
                "for_violation": v_type,
                "priority": v.get("severity", "MEDIUM"),
                "recommendation": RECOMMENDATIONS[v_type],
            })

    return recs


# ---------- Risk score calculation ----------

SEVERITY_WEIGHTS = {
    "CRITICAL": 10,
    "HIGH": 7,
    "MEDIUM": 4,
    "LOW": 1,
    "INFO": 0,
}


def calculate_risk_score(violations: list[dict]) -> dict:
    """Calculate an overall risk score from 0-100 based on violations."""
    if not violations:
        return {"score": 0, "grade": "A", "label": "Excellent"}

    total_weight = sum(
        SEVERITY_WEIGHTS.get(v.get("severity", "MEDIUM"), 4)
        for v in violations
    )

    # Cap at 100
    score = min(total_weight, 100)

    if score >= 70:
        grade, label = "F", "Critical Risk"
    elif score >= 50:
        grade, label = "D", "High Risk"
    elif score >= 30:
        grade, label = "C", "Moderate Risk"
    elif score >= 10:
        grade, label = "B", "Low Risk"
    else:
        grade, label = "A", "Minimal Risk"

    return {"score": score, "grade": grade, "label": label}


# ---------- Main function ----------

def generate_report(
    ct_rules: dict,
    pii_report: list[dict],
    compliance_report: dict,
    appeals: dict,
    output_dir: str = "output",
) -> dict:
    """
    Synthesize all pipeline findings into a comprehensive audit report.

    Args:
        ct_rules: Structured rules from the Regulatory Analyst.
        pii_report: PII detection results from Data Forensics.
        compliance_report: Compliance violations from the Compliance Auditor.
        appeals: Appeals validation from the Appeals Processor.
        output_dir: Directory to save the report file.

    Returns:
        Complete audit report dict (also saved to disk).
    """
    # Gather all violations
    all_violations = []
    all_violations.extend(compliance_report.get("violations", []))
    all_violations.extend(appeals.get("violations", []))

    # Calculate risk
    risk = calculate_risk_score(all_violations)

    # Generate recommendations
    recommendations = generate_recommendations(all_violations)

    # Build the report
    report = {
        "metadata": {
            "report_title": "Connecticut Data Privacy Act (CTDPA) Compliance Audit",
            "generated_at": datetime.now().isoformat(),
            "framework": "CTDPA (Conn. Gen. Stat. Sec. 42-515 et seq.)",
            "scope": "Connecticut only",
            "model_cost": "$0.00 (Local processing)",
        },
        "executive_summary": {
            "overall_status": "FAIL" if all_violations else "PASS",
            "risk_assessment": risk,
            "total_violations": len(all_violations),
            "critical_violations": sum(1 for v in all_violations if v.get("severity") == "CRITICAL"),
            "high_violations": sum(1 for v in all_violations if v.get("severity") == "HIGH"),
        },
        "regulatory_analysis": {
            "applicable_rules": ct_rules,
        },
        "pii_findings": {
            "files_analyzed": len(pii_report),
            "total_unique_consumers": sum(
                r.get("unique_consumers", 0) for r in pii_report if "error" not in r
            ),
            "pii_types_detected": list(set(
                pii_type
                for r in pii_report if "error" not in r
                for pii_type in r.get("pii_detected", [])
            )),
            "details": pii_report,
        },
        "compliance_findings": compliance_report,
        "appeals_findings": appeals,
        "violations": all_violations,
        "recommendations": recommendations,
    }

    # Save to disk
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_path / f"ctdpa_audit_report_{timestamp}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    report["_saved_to"] = str(filepath)
    return report
