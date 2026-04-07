"""
Ground truth data for evaluating the CT Data Privacy Auditor.

The sample ground truth is derived from the known, intentional flaws
in src/generate_dummy_data.py (seed=42):
  - ACME Corp policy is missing: delete, portability, opt-out, appeal
  - ACME Corp policy has: access (Section 4a), correct (Section 4b)
  - business_data.csv has 36K records with PII + CTDPA sensitive categories
  - request_log.csv has ~20% late and ~5% very late responses
"""

import csv
from datetime import datetime
from pathlib import Path


# ------------------------------------------------------------------ #
# Ground truth for the ACME sample dataset                            #
# ------------------------------------------------------------------ #

SAMPLE_GROUND_TRUTH = {
    # -- Violations the auditor SHOULD find --
    "expected_violations": [
        {"type": "MISSING_RIGHT", "right": "delete", "severity": "HIGH"},
        {"type": "MISSING_RIGHT", "right": "portability", "severity": "MEDIUM"},
        {"type": "MISSING_RIGHT", "right": "opt-out", "severity": "HIGH"},
        {"type": "MISSING_RIGHT", "right": "appeal", "severity": "MEDIUM"},
        # Sensitive data is present in CSVs but not disclosed in policy
        {"type": "UNDISCLOSED_SENSITIVE_DATA", "data_category": "health_data", "severity": "CRITICAL"},
        {"type": "UNDISCLOSED_SENSITIVE_DATA", "data_category": "racial_ethnic", "severity": "CRITICAL"},
        {"type": "UNDISCLOSED_SENSITIVE_DATA", "data_category": "religious", "severity": "CRITICAL"},
    ],

    # -- Violations the auditor should NOT find (rights ARE in the policy) --
    "expected_non_violations": [
        {"type": "MISSING_RIGHT", "right": "access"},
        {"type": "MISSING_RIGHT", "right": "correct"},
    ],

    # -- PII types that SHOULD be detected in business_data.csv --
    "expected_pii_types": [
        # Regex-detectable
        "email", "ssn", "phone", "date_of_birth",
        # Keyword-detectable (CTDPA sensitive categories)
        "health_data", "racial_ethnic", "religious",
        "geolocation", "neural_data", "genetic_data",
        "sexual_orientation", "biometric_data",
    ],

    # -- Per-right coverage in the business policy --
    "expected_rights_coverage": {
        "access": True,       # Section 4(a): "request a copy of the personal data"
        "correct": True,      # Section 4(b): "request a correction"
        "delete": False,      # Not mentioned
        "portability": False,  # Not mentioned
        "opt-out": False,     # Not mentioned (mentions sharing, no opt-out mechanism)
        "appeal": False,      # Not mentioned
    },

    # -- Appeals --
    "expected_appeal_status": {
        "has_appeal": False,
        "quality": "MISSING",
    },

    # -- Overall expected outcome --
    "expected_compliance_status": "Non-Compliant",
    "total_ctdpa_clauses": 6,  # 6 consumer rights
}


def compute_timeline_ground_truth(request_log_path: str | None = None) -> dict:
    """Compute timeline ground truth from the sample request_log.csv.

    Returns counts of on-time, late (>45 days), and very late (>90 days)
    responses. Computed dynamically to stay in sync with the CSV.
    """
    if request_log_path is None:
        base = Path(__file__).resolve().parent.parent.parent
        request_log_path = str(base / "Data" / "sample" / "request_logs" / "request_log.csv")

    path = Path(request_log_path)
    if not path.exists():
        return {"total": 0, "on_time": 0, "late": 0, "very_late": 0}

    total = 0
    on_time = 0
    late = 0
    very_late = 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            req_date_str = row.get("request_date", "").strip()
            resp_date_str = row.get("response_date", "").strip()
            if not req_date_str or not resp_date_str:
                continue
            try:
                req_date = datetime.strptime(req_date_str, "%Y-%m-%d")
                resp_date = datetime.strptime(resp_date_str, "%Y-%m-%d")
                days = (resp_date - req_date).days
                total += 1
                if days > 90:
                    very_late += 1
                elif days > 45:
                    late += 1
                else:
                    on_time += 1
            except ValueError:
                continue

    return {
        "total": total,
        "on_time": on_time,
        "late": late,
        "very_late": very_late,
    }


# ------------------------------------------------------------------ #
# JSON schema for custom ground truth uploads                         #
# ------------------------------------------------------------------ #

GROUND_TRUTH_SCHEMA = {
    "required_keys": [
        "expected_violations",
        "expected_pii_types",
        "expected_rights_coverage",
        "expected_compliance_status",
    ],
    "optional_keys": [
        "expected_non_violations",
        "expected_appeal_status",
        "total_ctdpa_clauses",
    ],
}


def validate_ground_truth(gt: dict) -> tuple[bool, str]:
    """Validate a ground truth dict against the expected schema."""
    for key in GROUND_TRUTH_SCHEMA["required_keys"]:
        if key not in gt:
            return False, f"Missing required key: '{key}'"
    return True, "Valid"
