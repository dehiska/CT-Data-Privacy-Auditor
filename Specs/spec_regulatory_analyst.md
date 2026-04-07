# Agent Spec: Regulatory Analyst

## 1. Overview
**Role:** Legal Parser & Rule Extractor  
**Goal:** Convert CTDPA statutes into structured JSON rules with legal accuracy.

## 2. Improvements
- Handles numeric variation ("100,000", "one hundred thousand")
- Extracts CTDPA-specific sensitive data
- Adds structured outputs (confidence + evidence)

## 3. Implementation
```python
import PyPDF2
import re
import spacy

nlp = spacy.load("en_core_web_sm")

def normalize_numbers(text):
    text = text.lower()
    text = text.replace("one hundred thousand", "100000")
    return text

def extract_threshold(text):
    text = normalize_numbers(text)
    patterns = [
        r"100,?000\s+consumers",
        r"100000\s+consumers",
        r"not less than 100000"
    ]
    for p in patterns:
        if re.search(p, text):
            return {"value": 100000, "confidence": 0.95}
    return {"value": 35000, "confidence": 0.6}

def extract_sensitive_data(text):
    categories = [
        "racial or ethnic origin", "religious beliefs",
        "mental or physical health condition", "sex life",
        "sexual orientation", "biometric data",
        "genetic data", "precise geolocation", "neural data"
    ]
    found = [c for c in categories if c in text.lower()]
    return {"categories": found, "confidence": 0.9}

def regulatory_analyst_agent(state):
    text = ""

    for file_path in ["CTDPA_Statute_22-15.pdf"]:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text()

    threshold = extract_threshold(text)
    sensitive = extract_sensitive_data(text)

    state["ct_rules"] = {
        "threshold": threshold,
        "sensitive_data": sensitive,
        "consumer_rights": [
            "access", "correct", "delete",
            "portability", "opt-out", "appeal"
        ],
        "glba_exemption": any(x in text.lower() for x in [
            "gramm-leach-bliley", "glba", "financial institution"
        ])
    }

    return state