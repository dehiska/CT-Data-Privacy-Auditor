"""
Shared state management for the CT Data Privacy Auditor pipeline.

The state dict flows through agents sequentially:
  Regulatory Analyst -> Data Forensics -> Compliance Auditor -> Appeals Processor -> Report Generator

Each agent reads from and writes to specific keys.
"""

import json
from pathlib import Path
from datetime import datetime


def create_initial_state(
    business_policy: str,
    business_data_paths: list[str],
    request_log_path: str | None = None,
    pdf_directory: str | None = None,
) -> dict:
    """Create the initial state dict that flows through the agent pipeline."""
    return {
        # --- Inputs ---
        "business_policy": business_policy,
        "business_data": business_data_paths,
        "request_log": request_log_path,
        "pdf_directory": pdf_directory,

        # --- Populated by Regulatory Analyst ---
        "ct_rules": None,

        # --- Populated by Data Forensics ---
        "pii_report": None,

        # --- Populated by Compliance Auditor ---
        "compliance_report": None,

        # --- Populated by Appeals Processor ---
        "appeals": None,

        # --- Populated by Report Generator ---
        "final_report": None,

        # --- Metadata ---
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "pipeline_status": "initialized",
        },
    }


def save_state(state: dict, output_dir: str = "output") -> str:
    """Save the current state to a JSON file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"audit_state_{timestamp}.json"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)

    return str(filepath)


def save_report(report: dict, output_dir: str = "output") -> str:
    """Save the final audit report to a JSON file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"audit_report_{timestamp}.json"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    return str(filepath)
