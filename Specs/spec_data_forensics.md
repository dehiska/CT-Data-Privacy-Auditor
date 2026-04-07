# Agent Spec: Data Forensics

## 1. Overview
**Role:** Hybrid PII Detection Engine  
**Goal:** Detect PII using Kaggle-trained model + regex + CTDPA extensions

## 2. Key Design
- Hybrid detection (ML + regex)
- Confidence scoring
- No raw PII storage
- Unique consumer counting

## 3. Implementation
```python
import pandas as pd
import re
import joblib

# Load trained model (train separately on Kaggle dataset)
model = joblib.load("pii_model.pkl")

REGEX_PATTERNS = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
}

CTDPA_KEYWORDS = {
    "health_data": ["diagnosis", "treatment", "medical"],
    "biometric_data": ["fingerprint", "iris", "face scan"],
    "neural_data": ["eeg", "brainwave", "neural signal"]
}

def detect_regex(text):
    found = []
    for k, pattern in REGEX_PATTERNS.items():
        if re.search(pattern, text):
            found.append({"type": k, "confidence": 0.95})
    return found

def detect_keywords(text):
    found = []
    for k, words in CTDPA_KEYWORDS.items():
        if any(w in text.lower() for w in words):
            found.append({"type": k, "confidence": 0.7})
    return found

def detect_ml(text):
    preds = model.predict([text])
    return [{"type": p, "confidence": 0.8} for p in preds]

def get_sample(df):
    sample = df.sample(min(5, len(df)))
    return " ".join(sample.astype(str).stack())

def data_forensics_agent(state):
    results = []

    for file_path in state.get("business_data", []):
        df = pd.read_csv(file_path)

        text = get_sample(df)

        detections = (
            detect_regex(text)
            + detect_keywords(text)
            + detect_ml(text)
        )

        unique_users = df["customer_id"].nunique() if "customer_id" in df.columns else len(df)

        results.append({
            "file": file_path,
            "pii_detected": list({d["type"] for d in detections}),
            "confidence": sum(d["confidence"] for d in detections)/len(detections) if detections else 0,
            "unique_consumers": unique_users
        })

    state["pii_report"] = results
    return state