# Agent Spec: Compliance Auditor

## 1. Overview
**Role:** Legal Reasoning Engine  
**Goal:** Compare law vs policy vs detected data

## 2. Improvements
- Semantic similarity (GDPR dataset training)
- Evidence tracking
- Confidence scoring

## 3. Implementation
```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("all-MiniLM-L6-v2")

def similar(a, b):
    return cosine_similarity([model.encode(a)], [model.encode(b)])[0][0]

def compliance_auditor_agent(state):
    policy = state.get("business_policy", "")
    rules = state.get("ct_rules", {})
    pii = state.get("pii_report", [])

    violations = []

    for right in rules["consumer_rights"]:
        score = similar(policy, f"right to {right}")
        if score < 0.7:
            violations.append({
                "type": "MISSING_RIGHT",
                "right": right,
                "confidence": 1 - score
            })

    for file in pii:
        if "health_data" in file["pii_detected"] and "health" not in policy.lower():
            violations.append({
                "type": "UNDISCLOSED_SENSITIVE_DATA",
                "confidence": 0.9,
                "source": file["file"]
            })

    state["compliance_report"] = {
        "violations": violations,
        "status": "Non-Compliant" if violations else "Compliant"
    }

    return state