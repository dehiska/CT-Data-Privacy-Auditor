"""
Generate realistic dummy business data for CTDPA compliance testing.

Uses Faker to produce:
  - business_data.csv       (customer records with PII and sensitive data)
  - request_log.csv         (consumer rights requests, some intentionally late)
  - business_policy.txt     (intentionally flawed privacy policy for audit testing)

Usage:
    python -m src.generate_dummy_data [--records 36000] [--output-dir sample_data]
"""

import argparse
import random
from datetime import timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

# ── CT towns for realistic addresses ─────────────────────────────────
CT_TOWNS = [
    "Hartford", "New Haven", "Stamford", "Bridgeport", "Waterbury",
    "Norwalk", "Danbury", "Bristol", "Milford", "West Hartford",
    "Greenwich", "Fairfield", "Middletown", "Torrington", "Shelton",
    "Norwich", "New London", "Glastonbury", "Enfield", "Manchester",
]

CT_ZIPS = [
    "06103", "06510", "06901", "06601", "06702",
    "06850", "06810", "06010", "06460", "06117",
    "06830", "06824", "06457", "06790", "06484",
    "06360", "06320", "06033", "06082", "06040",
]

# ── Sensitive data fields (CTDPA categories) ─────────────────────────
DIAGNOSES = [
    "Hypertension", "Diabetes Type 2", "Anxiety disorder", "Depression",
    "Chronic back pain", "Asthma", "Migraine", "ADHD", "PTSD",
    "Bipolar disorder", "Hypothyroidism", "Sleep apnea", "Arthritis",
    "Celiac disease", "Fibromyalgia", "",
]

TREATMENTS = [
    "Medication therapy", "Insulin management", "Cognitive behavioral therapy",
    "Physical therapy", "Inhaler therapy", "Medication and counseling",
    "Occupational therapy", "Dietary management", "Surgery scheduled",
    "Biofeedback sessions", "",
]

RACIAL_ETHNIC = [
    "White", "Black or African American", "Hispanic or Latino",
    "Asian", "Native American", "Pacific Islander", "Two or More Races", "",
]

RELIGIONS = [
    "Christian", "Jewish", "Muslim", "Hindu", "Buddhist",
    "Agnostic", "Atheist", "Unitarian", "Sikh", "",
]

# Notes field seeds sensitive keywords the auditor should flag
NOTES_POOL = [
    "Standard account",
    "Requires neural data processing",
    "Health history attached",
    "Biometric scan on file",
    "Geolocation tracking enabled",
    "Sexual orientation disclosed in intake form",
    "Citizenship status verified",
    "Immigration records referenced",
    "Genetic testing results on file",
    "Union membership noted",
    "",
    "",
    "",
    "",  # blanks are common
]

REQUEST_TYPES = ["access", "delete", "correct", "opt-out", "portability", "appeal"]


# ── Generators ────────────────────────────────────────────────────────

def generate_business_data(num_records: int = 36000) -> pd.DataFrame:
    """Generate customer records with PII and CTDPA-sensitive data."""
    rows = []
    for i in range(1, num_records + 1):
        town_idx = random.randint(0, len(CT_TOWNS) - 1)

        # ~60% of records get health data (to trigger PII detection)
        has_health = random.random() < 0.6
        diagnosis = random.choice(DIAGNOSES) if has_health else ""
        treatment = random.choice(TREATMENTS) if diagnosis else ""

        # ~30% get racial/ethnic data, ~20% get religion
        racial = random.choice(RACIAL_ETHNIC) if random.random() < 0.3 else ""
        religion = random.choice(RELIGIONS) if random.random() < 0.2 else ""

        rows.append({
            "customer_id": f"C{i:06d}",
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.email(),
            "phone": f"{random.choice(['860','203','475'])}-{fake.numerify('###-####')}",
            "ssn": fake.ssn(),
            "address": fake.street_address(),
            "city": CT_TOWNS[town_idx],
            "state": "CT",
            "zip": CT_ZIPS[town_idx],
            "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=85).strftime("%m/%d/%Y"),
            "diagnosis": diagnosis,
            "treatment_plan": treatment,
            "racial_ethnic_origin": racial,
            "religion": religion,
            "notes": random.choice(NOTES_POOL),
            "account_status": random.choice(["Active"] * 8 + ["Inactive"] * 2),
        })

    return pd.DataFrame(rows)


def generate_request_log(num_customers: int, num_requests: int = 500) -> pd.DataFrame:
    """Generate consumer rights request log with some intentionally late responses."""
    rows = []
    for i in range(1, num_requests + 1):
        cust_id = f"C{random.randint(1, num_customers):06d}"
        req_type = random.choice(REQUEST_TYPES)
        req_date = fake.date_between(start_date="-1y", end_date="today")

        # CTDPA: 45-day response deadline
        # ~20% of requests are late (>45 days), ~5% are very late (>90 days)
        roll = random.random()
        if roll < 0.05:
            days = random.randint(91, 150)  # very late
        elif roll < 0.20:
            days = random.randint(46, 90)   # late
        else:
            days = random.randint(1, 44)    # on time

        resp_date = req_date + timedelta(days=days)
        status = random.choice(["completed"] * 9 + ["pending"])

        rows.append({
            "request_id": f"R{i:04d}",
            "customer_id": cust_id,
            "request_type": req_type,
            "request_date": req_date.isoformat(),
            "response_date": resp_date.isoformat(),
            "status": status,
        })

    return pd.DataFrame(rows)


def generate_flawed_policy() -> str:
    """Generate an intentionally flawed privacy policy for testing.

    Missing: delete rights, data portability, opt-out of profiling, appeal procedure.
    Present: access, correction (partial).
    """
    return """ACME CORPORATION PRIVACY POLICY
Effective Date: January 1, 2024

1. INTRODUCTION
ACME Corporation ("we", "us", "our") respects the privacy of our customers.
This policy describes how we collect, use, and share personal data.

2. DATA WE COLLECT
We collect the following categories of personal data:
- Contact information (name, email, phone, address)
- Date of birth
- Account and transaction history
- Health-related data for wellness program participants
- Device and browser information

3. HOW WE USE YOUR DATA
We use personal data for:
- Providing and improving our services
- Processing transactions
- Marketing and promotional communications
- Analytics and profiling to personalize your experience
- Sharing with trusted third-party partners

4. YOUR RIGHTS
(a) Right to Access: You may request a copy of the personal data we hold about you.
    To submit a request, email privacy@acmecorp.example.com.
(b) Right to Correction: If your data is inaccurate, you may request a correction.

5. DATA RETENTION
We retain personal data for as long as necessary to fulfill the purposes described
in this policy, or as required by law.

6. SECURITY
We implement reasonable security measures to protect your personal data from
unauthorized access, disclosure, or destruction.

7. CHILDREN'S PRIVACY
Our services are not directed to individuals under 16. We do not knowingly
collect data from children under 16.

8. CHANGES TO THIS POLICY
We may update this policy from time to time. We will notify you of material
changes by posting the updated policy on our website.

9. CONTACT US
For questions about this policy, contact us at:
Email: privacy@acmecorp.example.com
Phone: 860-555-0000
Address: 100 Corporate Plaza, Hartford, CT 06103
"""


def main():
    parser = argparse.ArgumentParser(description="Generate dummy CTDPA test data")
    parser.add_argument("--records", type=int, default=36000, help="Number of customer records")
    parser.add_argument("--requests", type=int, default=500, help="Number of request log entries")
    parser.add_argument("--output-dir", type=str, default="sample_data", help="Output directory")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    out = base_dir / args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.records:,} customer records...")
    biz_df = generate_business_data(args.records)
    biz_path = out / "business_data.csv"
    biz_df.to_csv(biz_path, index=False)
    print(f"  -> {biz_path} ({len(biz_df):,} rows)")

    print(f"Generating {args.requests} consumer request log entries...")
    log_df = generate_request_log(args.records, args.requests)
    log_path = out / "request_log.csv"
    log_df.to_csv(log_path, index=False)
    print(f"  -> {log_path} ({len(log_df)} rows)")

    print("Generating flawed privacy policy...")
    policy_path = out / "business_policy.txt"
    policy_path.write_text(generate_flawed_policy(), encoding="utf-8")
    print(f"  -> {policy_path}")

    print("\nDone! Files ready for audit testing.")


if __name__ == "__main__":
    main()
