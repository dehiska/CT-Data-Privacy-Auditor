"""
MCP Server for CT Data Privacy Auditor

Exposes 5 tools (one per agent specialty) as an in-process SDK MCP server.
Uses the @tool decorator from claude_agent_sdk.

Agents call these tools as mcp__ctdpa__<tool_name>.
"""

import json
from typing import Annotated

from claude_agent_sdk import tool, create_sdk_mcp_server

from src.tools.regulatory import parse_ctdpa_statutes
from src.tools.forensics import detect_pii
from src.tools.compliance import check_compliance
from src.tools.appeals import validate_appeals
from src.tools.report import generate_report


def _safe_parse_json(value: str) -> dict | list:
    """Parse a JSON string, handling double-serialization.

    Agents sometimes return a JSON string wrapped in another JSON string
    (e.g., '"{\\"key\\": \\"val\\"}"'). This unwraps until we get a
    dict or list.
    """
    parsed = json.loads(value)
    # Keep unwrapping if we got a string back (double-serialized)
    while isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            break
    # If we still have a string, wrap it so callers can .get() safely
    if isinstance(parsed, str):
        return {"raw": parsed}
    return parsed


# ---------- Tool 1: Regulatory Analyst ----------

@tool(
    "parse_ct_statutes",
    "Parse CTDPA statute PDFs and extract structured legal rules including thresholds, sensitive data categories, consumer rights, exemptions, and timelines.",
    {"pdf_directory": Annotated[str, "Path to directory containing CTDPA PDF files"]},
)
async def parse_ct_statutes_tool(args):
    result = parse_ctdpa_statutes(args["pdf_directory"])
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ---------- Tool 2: Data Forensics ----------

@tool(
    "detect_pii_in_data",
    "Detect PII in business data CSV files using hybrid regex, keyword, and ML detection. Never stores raw PII.",
    {"csv_file_paths": Annotated[list[str], "List of paths to CSV files containing business data"]},
)
async def detect_pii_tool(args):
    result = detect_pii(args["csv_file_paths"])
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ---------- Tool 3: Compliance Auditor ----------

@tool(
    "check_ctdpa_compliance",
    "Check business CTDPA compliance by comparing privacy policy against legal rules and detected PII using semantic similarity.",
    {
        "business_policy": Annotated[str, "Full text of the business privacy policy"],
        "ct_rules_json": Annotated[str, "JSON string of CTDPA rules from parse_ct_statutes"],
        "pii_report_json": Annotated[str, "JSON string of PII results from detect_pii_in_data"],
    },
)
async def check_compliance_tool(args):
    ct_rules = _safe_parse_json(args["ct_rules_json"])
    pii_report = _safe_parse_json(args["pii_report_json"])
    # pii_report can be {"pii_report": [...]} or [...]
    if isinstance(pii_report, dict) and "pii_report" in pii_report:
        pii_report = pii_report["pii_report"]
    if not isinstance(pii_report, list):
        pii_report = [pii_report] if pii_report else []
    result = check_compliance(args["business_policy"], ct_rules, pii_report)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ---------- Tool 4: Appeals Processor ----------

@tool(
    "validate_appeal_procedures",
    "Validate appeal procedures in the business privacy policy and check response timelines against the CTDPA 45-day limit.",
    {
        "business_policy": Annotated[str, "Full text of the business privacy policy"],
        "request_log_path": Annotated[str, "Optional path to CSV with request/response dates (empty string if none)"],
    },
)
async def validate_appeals_tool(args):
    log_path = args.get("request_log_path") or None
    result = validate_appeals(args["business_policy"], log_path)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ---------- Tool 5: Report Generator ----------

@tool(
    "generate_audit_report",
    "Generate a comprehensive CTDPA compliance audit report with risk scoring, violations, and recommendations.",
    {
        "ct_rules_json": Annotated[str, "JSON string of CTDPA rules"],
        "pii_report_json": Annotated[str, "JSON string of PII detection results"],
        "compliance_report_json": Annotated[str, "JSON string of compliance results"],
        "appeals_json": Annotated[str, "JSON string of appeals validation results"],
        "output_dir": Annotated[str, "Directory to save the report file (default: output)"],
    },
)
async def generate_report_tool(args):
    ct_rules = _safe_parse_json(args["ct_rules_json"])
    pii_report = _safe_parse_json(args["pii_report_json"])
    compliance_report = _safe_parse_json(args["compliance_report_json"])
    appeals = _safe_parse_json(args["appeals_json"])
    output_dir = args.get("output_dir", "output")

    # Normalize pii_report: extract the list if wrapped in {"pii_report": [...]}
    if isinstance(pii_report, dict) and "pii_report" in pii_report:
        pii_report = pii_report["pii_report"]
    if not isinstance(pii_report, list):
        pii_report = [pii_report] if pii_report else []

    result = generate_report(ct_rules, pii_report, compliance_report, appeals, output_dir)
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}


# ---------- Create the MCP server ----------

ALL_TOOLS = [
    parse_ct_statutes_tool,
    detect_pii_tool,
    check_compliance_tool,
    validate_appeals_tool,
    generate_report_tool,
]

ctdpa_server = create_sdk_mcp_server(
    name="ctdpa",
    version="1.0.0",
    tools=ALL_TOOLS,
)
