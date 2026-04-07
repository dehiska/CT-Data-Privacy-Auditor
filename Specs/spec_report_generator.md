# Agent Spec: Report Generator

from datetime import datetime

def report_generator_agent(state):

    violations = state.get("compliance_report", {}).get("violations", [])

    report = {
        "metadata": {
            "date": datetime.now().isoformat(),
            "budget": "$0.00 (Local)"
        },
        "summary": {
            "status": "FAIL" if violations else "PASS",
            "total_violations": len(violations)
        },
        "violations": violations,
        "pii_summary": state.get("pii_report", []),
        "appeals": state.get("appeals", {})
    }

    state["final_report"] = report
    return state