"""
Regulatory Analyst Tool - Legal Parser & Rule Extractor

Converts CTDPA statutes (PDFs) into structured JSON rules with legal accuracy.
Handles numeric variation, extracts CTDPA-specific sensitive data categories,
and produces structured outputs with confidence scores.
"""

import re
from pathlib import Path

import PyPDF2
import spacy


# Load spacy model for NLP processing
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None
    print("WARNING: spacy model 'en_core_web_sm' not found. Run: python -m spacy download en_core_web_sm")


# ---------- Number normalization ----------

WORD_TO_NUM = {
    "one hundred thousand": "100000",
    "thirty-five thousand": "35000",
    "thirty five thousand": "35000",
    "forty-five": "45",
    "forty five": "45",
    "sixty": "60",
    "ninety": "90",
    "one hundred": "100",
}


def normalize_numbers(text: str) -> str:
    """Convert written-out numbers to digits for reliable pattern matching."""
    text_lower = text.lower()
    for word, digit in WORD_TO_NUM.items():
        text_lower = text_lower.replace(word, digit)
    return text_lower


# ---------- Threshold extraction ----------

def extract_threshold(text: str) -> dict:
    """Extract the consumer-count threshold that triggers CTDPA applicability."""
    normalized = normalize_numbers(text)
    high_threshold_patterns = [
        r"100[,.]?000\s+consumers",
        r"100000\s+consumers",
        r"not\s+less\s+than\s+100[,.]?000",
        r"personal\s+data\s+of.*?100[,.]?000",
    ]
    for pattern in high_threshold_patterns:
        if re.search(pattern, normalized):
            return {"value": 100000, "unit": "consumers", "confidence": 0.95}

    low_threshold_patterns = [
        r"35[,.]?000\s+consumers",
        r"35000\s+consumers",
        r"derives.*revenue.*sale.*personal\s+data.*35[,.]?000",
    ]
    for pattern in low_threshold_patterns:
        if re.search(pattern, normalized):
            return {"value": 35000, "unit": "consumers", "confidence": 0.90}

    return {"value": None, "unit": "consumers", "confidence": 0.3, "note": "threshold not clearly identified"}


# ---------- Sensitive data extraction ----------

CTDPA_SENSITIVE_CATEGORIES = [
    "racial or ethnic origin",
    "religious beliefs",
    "mental or physical health condition",
    "mental or physical health diagnosis",
    "sex life",
    "sexual orientation",
    "citizenship or immigration status",
    "biometric data",
    "genetic data",
    "precise geolocation",
    "neural data",
    "personal data of a known child",
]


def extract_sensitive_data_categories(text: str) -> dict:
    """Identify which CTDPA sensitive data categories are mentioned in the statute."""
    text_lower = text.lower()
    found = []
    for category in CTDPA_SENSITIVE_CATEGORIES:
        if category in text_lower:
            found.append(category)

    return {
        "categories": found,
        "total_found": len(found),
        "total_possible": len(CTDPA_SENSITIVE_CATEGORIES),
        "confidence": 0.9 if found else 0.4,
    }


# ---------- Consumer rights extraction ----------

CTDPA_CONSUMER_RIGHTS = {
    "access": ["right to access", "right to confirm", "confirm whether", "access personal data"],
    "correct": ["right to correct", "correct inaccuracies"],
    "delete": ["right to delete", "deletion of personal data", "right to request deletion"],
    "portability": ["right to obtain", "portable", "data portability", "readily usable format"],
    "opt-out": ["right to opt out", "opt-out of the processing", "opt out of", "opt-out"],
    "appeal": ["right to appeal", "appeal a decision", "appeal process"],
}


def extract_consumer_rights(text: str) -> dict:
    """Extract consumer rights defined in the CTDPA."""
    text_lower = text.lower()
    found_rights = []
    evidence = {}

    for right, keywords in CTDPA_CONSUMER_RIGHTS.items():
        for kw in keywords:
            if kw in text_lower:
                found_rights.append(right)
                evidence[right] = kw
                break

    return {
        "rights": list(set(found_rights)),
        "evidence": evidence,
        "confidence": 0.85 if len(found_rights) >= 4 else 0.6,
    }


# ---------- Exemption extraction ----------

EXEMPTION_PATTERNS = {
    "glba": ["gramm-leach-bliley", "glba", "financial institution"],
    "hipaa": ["hipaa", "health insurance portability", "protected health information"],
    "ferpa": ["ferpa", "family educational rights"],
    "coppa": ["coppa", "children's online privacy"],
    "fcra": ["fair credit reporting", "fcra"],
    "nonprofit": ["nonprofit", "non-profit", "not-for-profit"],
    "government": ["state agency", "political subdivision", "government entity"],
    "higher_education": ["institution of higher education", "higher education"],
}


def extract_exemptions(text: str) -> dict:
    """Identify entity/data exemptions mentioned in the CTDPA."""
    text_lower = text.lower()
    found = {}

    for exemption, keywords in EXEMPTION_PATTERNS.items():
        matched = any(kw in text_lower for kw in keywords)
        found[exemption] = matched

    return {
        "exemptions": {k: v for k, v in found.items() if v},
        "confidence": 0.85,
    }


# ---------- Timeline requirements ----------

def extract_timelines(text: str) -> dict:
    """Extract key response-time and compliance timelines from the statute."""
    text_lower = normalize_numbers(text.lower())
    timelines = {}

    # Response to consumer requests
    response_patterns = [
        (r"(\d+)\s*(?:calendar\s+)?days.*(?:respond|response|request)", "consumer_request_response_days"),
        (r"without\s+undue\s+delay.*?(\d+)\s*days", "consumer_request_response_days"),
    ]
    for pattern, key in response_patterns:
        match = re.search(pattern, text_lower)
        if match:
            timelines[key] = int(match.group(1))

    # Cure period
    cure_patterns = [r"(\d+)\s*(?:calendar\s+)?days.*(?:cure|correct|remedy)"]
    for pattern in cure_patterns:
        match = re.search(pattern, text_lower)
        if match:
            timelines["cure_period_days"] = int(match.group(1))

    # Appeal response
    appeal_patterns = [r"(\d+)\s*(?:calendar\s+)?days.*appeal"]
    for pattern in appeal_patterns:
        match = re.search(pattern, text_lower)
        if match:
            timelines["appeal_response_days"] = int(match.group(1))

    # Default timelines per CTDPA if not explicitly found
    if "consumer_request_response_days" not in timelines:
        timelines["consumer_request_response_days"] = 45
        timelines["_response_days_source"] = "CTDPA default"

    return {"timelines": timelines, "confidence": 0.8 if len(timelines) > 1 else 0.5}


# ---------- Main function ----------

def parse_ctdpa_statutes(pdf_directory: str) -> dict:
    """
    Parse all CT law PDFs in the given directory and extract structured legal rules.

    Args:
        pdf_directory: Path to directory containing CTDPA PDF files.

    Returns:
        Structured dict with threshold, sensitive_data, consumer_rights,
        exemptions, timelines, and metadata.
    """
    pdf_dir = Path(pdf_directory)
    if not pdf_dir.exists():
        return {"error": f"Directory not found: {pdf_directory}"}

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        return {"error": f"No PDF files found in: {pdf_directory}"}

    # Extract text from all PDFs
    all_text = ""
    file_metadata = []

    for pdf_path in pdf_files:
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                file_text = ""
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    file_text += page_text + "\n"
                all_text += file_text
                file_metadata.append({
                    "file": pdf_path.name,
                    "pages": len(reader.pages),
                    "chars_extracted": len(file_text),
                })
        except Exception as e:
            file_metadata.append({
                "file": pdf_path.name,
                "error": str(e),
            })

    # Run all extractors
    threshold = extract_threshold(all_text)
    sensitive_data = extract_sensitive_data_categories(all_text)
    consumer_rights = extract_consumer_rights(all_text)
    exemptions = extract_exemptions(all_text)
    timelines = extract_timelines(all_text)

    return {
        "threshold": threshold,
        "sensitive_data": sensitive_data,
        "consumer_rights": consumer_rights,
        "exemptions": exemptions,
        "timelines": timelines,
        "source_files": file_metadata,
        "total_text_length": len(all_text),
    }
