"""
Data Forensics Tool - Hybrid PII Detection Engine

Detects PII using a three-pronged approach:
  1. Regex patterns (email, SSN, phone)
  2. CTDPA-specific keyword matching (health, biometric, neural data)
  3. ML model predictions (TF-IDF + LogisticRegression)

Key design principles:
  - No raw PII is stored, only detection metadata
  - Confidence scoring for all detections
  - Unique consumer counting for CTDPA threshold checks
"""

import re
from pathlib import Path

import pandas as pd

try:
    import joblib
except ImportError:
    joblib = None


# ---------- Regex-based PII detection ----------

REGEX_PATTERNS = {
    "email": r"[\w\.\-\+]+@[\w\.\-]+\.\w{2,}",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    "date_of_birth": r"\b(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b",
}


def detect_regex(text: str) -> list[dict]:
    """Detect PII using regex patterns. Returns list of detection dicts."""
    found = []
    for pii_type, pattern in REGEX_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            found.append({
                "type": pii_type,
                "method": "regex",
                "count": len(matches),
                "confidence": 0.95,
            })
    return found


# ---------- CTDPA keyword-based detection ----------

CTDPA_KEYWORDS = {
    "health_data": [
        "diagnosis", "treatment", "medical", "prescription", "health condition",
        "mental health", "physical health", "patient", "clinical",
    ],
    "biometric_data": [
        "fingerprint", "iris", "face scan", "facial recognition", "retina",
        "voiceprint", "palm print", "gait", "biometric",
    ],
    "neural_data": [
        "eeg", "brainwave", "neural signal", "brain-computer", "neurofeedback",
        "neural data", "brain scan",
    ],
    "genetic_data": [
        "dna", "genetic", "genome", "chromosom", "hereditary",
    ],
    "geolocation": [
        "gps", "latitude", "longitude", "precise location", "geolocation",
        "geo-fence", "geofence",
    ],
    "racial_ethnic": [
        "race", "ethnicity", "ethnic origin", "racial",
    ],
    "religious": [
        "religion", "religious belief", "faith", "worship",
    ],
    "sexual_orientation": [
        "sexual orientation", "gender identity", "sex life",
    ],
}


def detect_keywords(text: str) -> list[dict]:
    """Detect CTDPA-sensitive data categories via keyword matching."""
    found = []
    text_lower = text.lower()

    for category, keywords in CTDPA_KEYWORDS.items():
        matched_keywords = [kw for kw in keywords if kw in text_lower]
        if matched_keywords:
            found.append({
                "type": category,
                "method": "keyword",
                "matched_terms": matched_keywords,
                "confidence": min(0.5 + 0.15 * len(matched_keywords), 0.9),
            })
    return found


# ---------- ML-based detection ----------

_ml_model = None


def _load_ml_model():
    """Lazy-load the trained PII detection model."""
    global _ml_model
    if _ml_model is not None:
        return _ml_model

    model_path = Path(__file__).parent.parent.parent / "models" / "pii_model.pkl"
    if model_path.exists() and joblib is not None:
        try:
            _ml_model = joblib.load(model_path)
            return _ml_model
        except Exception as e:
            print(f"WARNING: Could not load PII model: {e}")

    return None


def detect_ml(text: str) -> list[dict]:
    """Detect PII using the trained ML model. Falls back gracefully if model unavailable."""
    model = _load_ml_model()
    if model is None:
        return []

    try:
        predictions = model.predict([text])
        probabilities = model.predict_proba([text])

        results = []
        for i, label in enumerate(model.classes_):
            if label == "clean":
                continue
            prob = probabilities[0][i]
            if prob > 0.5:
                results.append({
                    "type": label,
                    "method": "ml_model",
                    "confidence": round(float(prob), 3),
                })
        return results
    except Exception as e:
        print(f"WARNING: ML detection failed: {e}")
        return []


# ---------- Sampling ----------

def get_text_sample(df: pd.DataFrame, sample_size: int = 5) -> str:
    """Extract a text sample from a DataFrame for PII scanning."""
    sample = df.sample(min(sample_size, len(df)), random_state=42)
    # Fill NaN before converting to string to avoid
    # "expected str instance, float found" error from .join()
    return " ".join(sample.fillna("").astype(str).stack().tolist())


def count_unique_consumers(df: pd.DataFrame) -> int:
    """Count unique consumers in the dataset for CTDPA threshold comparison."""
    # Try common ID column names
    id_columns = ["customer_id", "user_id", "consumer_id", "id", "email", "account_id"]
    for col in id_columns:
        if col in df.columns:
            return int(df[col].nunique())

    # Fallback: row count as upper bound
    return len(df)


# ---------- Main function ----------

def detect_pii(csv_file_paths: list[str]) -> dict:
    """
    Detect PII across one or more business data CSV files.

    Uses hybrid detection: regex + CTDPA keywords + ML model.
    Never stores raw PII - only detection metadata.

    Args:
        csv_file_paths: List of paths to CSV files containing business data.

    Returns:
        Dict with per-file PII detection results.
    """
    results = []

    for file_path in csv_file_paths:
        path = Path(file_path)
        if not path.exists():
            results.append({"file": file_path, "error": "File not found"})
            continue

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            results.append({"file": file_path, "error": f"Could not read CSV: {e}"})
            continue

        # Get text sample for detection
        text_sample = get_text_sample(df)

        # Run all three detection methods
        regex_hits = detect_regex(text_sample)
        keyword_hits = detect_keywords(text_sample)
        ml_hits = detect_ml(text_sample)

        all_detections = regex_hits + keyword_hits + ml_hits

        # Deduplicate by type, keeping highest confidence
        type_best = {}
        for d in all_detections:
            pii_type = d["type"]
            if pii_type not in type_best or d["confidence"] > type_best[pii_type]["confidence"]:
                type_best[pii_type] = d

        # Also scan column headers for PII indicators
        column_pii = detect_column_names(df.columns.tolist())

        # Count unique consumers
        unique_consumers = count_unique_consumers(df)

        # Aggregate confidence
        all_confs = [d["confidence"] for d in type_best.values()]
        avg_confidence = sum(all_confs) / len(all_confs) if all_confs else 0.0

        results.append({
            "file": path.name,
            "rows": len(df),
            "columns": len(df.columns),
            "pii_detected": list(type_best.keys()),
            "detection_details": list(type_best.values()),
            "column_pii_indicators": column_pii,
            "average_confidence": round(avg_confidence, 3),
            "unique_consumers": unique_consumers,
        })

    return {"pii_report": results}


def detect_column_names(columns: list[str]) -> list[dict]:
    """Check if column names themselves suggest PII content."""
    pii_column_hints = {
        "email": ["email", "e-mail", "email_address"],
        "name": ["name", "first_name", "last_name", "full_name"],
        "phone": ["phone", "telephone", "mobile", "cell"],
        "ssn": ["ssn", "social_security", "social_sec"],
        "address": ["address", "street", "city", "zip", "postal"],
        "dob": ["dob", "date_of_birth", "birth_date", "birthday"],
        "ip_address": ["ip", "ip_address"],
    }

    found = []
    for col in columns:
        col_lower = col.lower().strip()
        for pii_type, hints in pii_column_hints.items():
            if any(hint in col_lower for hint in hints):
                found.append({"column": col, "likely_pii_type": pii_type})
                break

    return found
