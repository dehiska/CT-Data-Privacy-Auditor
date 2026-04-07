"""
PII Detection Model Trainer

Generates synthetic training data and trains a TF-IDF + LogisticRegression
pipeline for PII type classification. The model supplements regex and keyword
detection in the Data Forensics tool.

Usage:
    python -m src.models.train_pii_model

Output:
    models/pii_model.pkl
"""

import random
import string
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report


# ---------- Synthetic data generators ----------

def random_email():
    user = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    domain = random.choice(["gmail.com", "yahoo.com", "outlook.com", "company.com", "example.org"])
    return f"{user}@{domain}"

def random_ssn():
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"

def random_phone():
    return f"{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"

def random_name():
    first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "David", "Elizabeth"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def random_address():
    streets = ["Main St", "Oak Ave", "Elm St", "Park Rd", "Cedar Ln", "Maple Dr"]
    cities = ["Hartford", "New Haven", "Stamford", "Bridgeport", "Waterbury", "Norwalk"]
    return f"{random.randint(1,9999)} {random.choice(streets)}, {random.choice(cities)}, CT {random.randint(6000,6999):05d}"

def random_health_text():
    terms = [
        "Patient diagnosed with hypertension and prescribed medication",
        "Treatment plan includes physical therapy sessions",
        "Medical history indicates prior diagnosis of diabetes",
        "Mental health assessment completed for anxiety disorder",
        "Clinical notes: patient reports chronic back pain",
        "Prescription for amoxicillin 500mg issued today",
        "Health condition requires ongoing monitoring of blood pressure",
    ]
    return random.choice(terms)

def random_biometric_text():
    terms = [
        "Fingerprint scan recorded for employee badge access",
        "Facial recognition data captured at entrance",
        "Iris scan required for secure area access",
        "Voiceprint enrolled for phone authentication",
        "Biometric template stored in encrypted database",
        "Palm print reader installed at security checkpoint",
    ]
    return random.choice(terms)

def random_neural_text():
    terms = [
        "EEG data collected during neurofeedback session",
        "Brainwave patterns analyzed for sleep study",
        "Neural signal recording from brain-computer interface",
        "Neurofeedback training session data for attention improvement",
        "Brain scan results indicate normal neural activity",
    ]
    return random.choice(terms)

def random_clean_text():
    terms = [
        "The quarterly sales report shows a 15% increase in revenue",
        "Meeting scheduled for next Tuesday to discuss project timeline",
        "Inventory levels are sufficient for the upcoming holiday season",
        "The software update includes performance improvements and bug fixes",
        "Company policy requires annual training for all employees",
        "The marketing campaign reached over 50000 impressions this month",
        "Budget allocation for Q3 has been approved by management",
        "New product launch is on track for September release date",
        "Team building event planned for Friday afternoon",
        "Vendor contract renewal is due by end of fiscal year",
    ]
    return random.choice(terms)


# ---------- Dataset generation ----------

def generate_training_data(samples_per_class: int = 150) -> tuple[list[str], list[str]]:
    """Generate synthetic training data with labels."""
    texts = []
    labels = []

    generators = {
        "email": lambda: f"Contact info: {random_email()} for account {random.randint(1000,9999)}",
        "ssn": lambda: f"Social security number: {random_ssn()} on file for verification",
        "phone": lambda: f"Phone number {random_phone()} listed as primary contact",
        "name": lambda: f"Customer name: {random_name()}, account holder since 2020",
        "address": lambda: f"Mailing address: {random_address()} for delivery",
        "health_data": random_health_text,
        "biometric_data": random_biometric_text,
        "neural_data": random_neural_text,
        "clean": random_clean_text,
    }

    for label, gen in generators.items():
        for _ in range(samples_per_class):
            texts.append(gen())
            labels.append(label)

    return texts, labels


# ---------- Training ----------

def train_model(output_path: str = "models/pii_model.pkl"):
    """Train the PII detection model and save it."""
    print("Generating synthetic training data...")
    texts, labels = generate_training_data(samples_per_class=150)

    print(f"  Total samples: {len(texts)}")
    print(f"  Classes: {sorted(set(labels))}")

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # Build pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000, random_state=42)),
    ])

    print("Training TF-IDF + LogisticRegression pipeline...")
    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    accuracy = pipeline.score(X_test, y_test)
    print(f"Accuracy: {accuracy:.3f}")

    # Save
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out)
    print(f"\nModel saved to: {out.resolve()}")

    return pipeline


if __name__ == "__main__":
    train_model()
