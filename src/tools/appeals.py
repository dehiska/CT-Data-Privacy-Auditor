"""
Appeals Processor Tool - Appeal Procedure Validator

Validates that a business's privacy policy includes appeal procedures
as required by the CTDPA, and checks response timelines against the
45-day statutory limit.
"""

from pathlib import Path

import pandas as pd


# ---------- Appeal procedure validation ----------

APPEAL_KEYWORDS = [
    "appeal",
    "dispute",
    "review decision",
    "reconsideration",
    "grievance",
    "contest",
    "challenge a decision",
]

APPEAL_REQUIREMENT_KEYWORDS = [
    "inform the consumer",
    "appeal process",
    "online mechanism",
    "how to appeal",
    "submit an appeal",
]


def has_appeal_procedure(policy_text: str) -> dict:
    """
    Check if the business policy describes an appeal procedure.

    The CTDPA requires controllers to establish a process for consumers
    to appeal the controller's refusal to take action on a request.
    """
    policy_lower = policy_text.lower()

    # Check for basic appeal mention
    basic_mentions = [kw for kw in APPEAL_KEYWORDS if kw in policy_lower]

    # Check for detailed appeal process
    detailed_mentions = [kw for kw in APPEAL_REQUIREMENT_KEYWORDS if kw in policy_lower]

    has_basic = len(basic_mentions) > 0
    has_detailed = len(detailed_mentions) > 0

    if has_detailed:
        return {
            "has_appeal": True,
            "quality": "DETAILED",
            "matched_terms": basic_mentions + detailed_mentions,
            "confidence": 0.95,
        }
    elif has_basic:
        return {
            "has_appeal": True,
            "quality": "BASIC",
            "matched_terms": basic_mentions,
            "confidence": 0.75,
            "recommendation": "Policy mentions appeals but lacks detail on the appeal process. Consider adding specific instructions for consumers.",
        }
    else:
        return {
            "has_appeal": False,
            "quality": "MISSING",
            "matched_terms": [],
            "confidence": 0.90,
        }


# ---------- Timeline validation ----------

CTDPA_RESPONSE_LIMIT_DAYS = 45
CTDPA_EXTENSION_LIMIT_DAYS = 45  # Can extend by additional 45 days with notice


def check_response_timelines(request_log_path: str) -> dict:
    """
    Analyze a request log CSV for responses exceeding the CTDPA 45-day limit.

    Expects columns: 'request' (or 'request_date') and 'response' (or 'response_date')
    with parseable date values.
    """
    path = Path(request_log_path)
    if not path.exists():
        return {"error": f"Request log not found: {request_log_path}"}

    try:
        df = pd.read_csv(request_log_path)
    except Exception as e:
        return {"error": f"Could not read request log: {e}"}

    # Find date columns
    request_col = None
    response_col = None

    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in ("request", "request_date", "date_requested", "submitted"):
            request_col = col
        elif col_lower in ("response", "response_date", "date_responded", "completed"):
            response_col = col

    if not request_col or not response_col:
        return {
            "error": f"Could not identify date columns. Found: {df.columns.tolist()}. Expected 'request'/'request_date' and 'response'/'response_date'."
        }

    try:
        df["_request_dt"] = pd.to_datetime(df[request_col], errors="coerce")
        df["_response_dt"] = pd.to_datetime(df[response_col], errors="coerce")
    except Exception as e:
        return {"error": f"Could not parse dates: {e}"}

    # Drop rows with unparseable dates
    valid = df.dropna(subset=["_request_dt", "_response_dt"])

    if len(valid) == 0:
        return {"error": "No valid date pairs found in request log."}

    # Calculate response times
    valid = valid.copy()
    valid["_days"] = (valid["_response_dt"] - valid["_request_dt"]).dt.days

    total_requests = len(valid)
    late_mask = valid["_days"] > CTDPA_RESPONSE_LIMIT_DAYS
    late_requests = valid[late_mask]

    # Extreme violations (beyond even the extension period)
    extreme_mask = valid["_days"] > (CTDPA_RESPONSE_LIMIT_DAYS + CTDPA_EXTENSION_LIMIT_DAYS)
    extreme_requests = valid[extreme_mask]

    return {
        "total_requests": total_requests,
        "late_responses": int(late_mask.sum()),
        "extreme_late_responses": int(extreme_mask.sum()),
        "late_percentage": round(late_mask.sum() / total_requests * 100, 1),
        "average_response_days": round(valid["_days"].mean(), 1),
        "max_response_days": int(valid["_days"].max()),
        "statutory_limit_days": CTDPA_RESPONSE_LIMIT_DAYS,
    }


# ---------- Main function ----------

def validate_appeals(
    business_policy: str,
    request_log_path: str | None = None,
) -> dict:
    """
    Validate appeal procedures and response timelines.

    Args:
        business_policy: Full text of the business's privacy policy.
        request_log_path: Optional path to CSV with request/response dates.

    Returns:
        Appeals validation report with violations and risk assessment.
    """
    violations = []

    # 1. Check appeal procedure in policy
    appeal_check = has_appeal_procedure(business_policy)

    if not appeal_check["has_appeal"]:
        violations.append({
            "type": "CRITICAL_NO_APPEAL",
            "severity": "CRITICAL",
            "description": "Business privacy policy does not include an appeal procedure. CTDPA Sec. 42-520(a)(4) requires controllers to establish a process for consumers to appeal.",
            "confidence": appeal_check["confidence"],
        })
    elif appeal_check["quality"] == "BASIC":
        violations.append({
            "type": "WEAK_APPEAL_PROCESS",
            "severity": "MEDIUM",
            "description": appeal_check.get("recommendation", "Appeal process lacks detail."),
            "confidence": appeal_check["confidence"],
        })

    # 2. Check response timelines if log provided
    timeline_result = None
    if request_log_path:
        timeline_result = check_response_timelines(request_log_path)

        if "error" not in timeline_result:
            if timeline_result["late_responses"] > 0:
                violations.append({
                    "type": "LATE_RESPONSE",
                    "severity": "HIGH",
                    "description": f"{timeline_result['late_responses']} of {timeline_result['total_requests']} consumer requests exceeded the {CTDPA_RESPONSE_LIMIT_DAYS}-day response limit.",
                    "late_count": timeline_result["late_responses"],
                    "total_count": timeline_result["total_requests"],
                    "late_percentage": timeline_result["late_percentage"],
                    "confidence": 0.95,
                })

            if timeline_result["extreme_late_responses"] > 0:
                violations.append({
                    "type": "EXTREME_LATE_RESPONSE",
                    "severity": "CRITICAL",
                    "description": f"{timeline_result['extreme_late_responses']} requests exceeded even the extended 90-day limit (45 + 45 extension).",
                    "confidence": 0.98,
                })

    # Determine risk level
    has_critical = any(v["severity"] == "CRITICAL" for v in violations)
    has_high = any(v["severity"] == "HIGH" for v in violations)

    if has_critical:
        risk = "CRITICAL"
    elif has_high:
        risk = "HIGH"
    elif violations:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "appeal_procedure": appeal_check,
        "timeline_analysis": timeline_result,
        "violations": violations,
        "risk": risk,
    }
