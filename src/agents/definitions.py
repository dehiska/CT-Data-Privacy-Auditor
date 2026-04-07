"""
Agent definitions for the CT Data Privacy Auditor multi-agent system.

Defines 5 subagents using the Claude Agent SDK's AgentDefinition,
each with a focused role, prompt, and access to specific MCP tools.
"""

from claude_agent_sdk import AgentDefinition

from src.agents.prompts import (
    REGULATORY_ANALYST_PROMPT,
    DATA_FORENSICS_PROMPT,
    COMPLIANCE_AUDITOR_PROMPT,
    APPEALS_PROCESSOR_PROMPT,
    REPORT_GENERATOR_PROMPT,
)

# Model for all subagents (Haiku for fast, cheap dev/testing)
AGENT_MODEL = "claude-haiku-4-5-20251001"


# ---------- Agent 1: Regulatory Analyst ----------

regulatory_analyst = AgentDefinition(
    description="Parses CTDPA statute PDFs and extracts structured legal rules including thresholds, sensitive data categories, consumer rights, and exemptions.",
    prompt=REGULATORY_ANALYST_PROMPT,
    model=AGENT_MODEL,
    tools=["mcp__ctdpa__parse_ct_statutes"],
    maxTurns=3,
)


# ---------- Agent 2: Data Forensics ----------

data_forensics = AgentDefinition(
    description="Detects PII in business data using hybrid regex, keyword, and ML detection. Counts unique consumers for CTDPA threshold checks.",
    prompt=DATA_FORENSICS_PROMPT,
    model=AGENT_MODEL,
    tools=["mcp__ctdpa__detect_pii_in_data"],
    maxTurns=3,
)


# ---------- Agent 3: Compliance Auditor ----------

compliance_auditor = AgentDefinition(
    description="Compares business privacy policy against CTDPA requirements using semantic similarity. Identifies missing rights and undisclosed sensitive data.",
    prompt=COMPLIANCE_AUDITOR_PROMPT,
    model=AGENT_MODEL,
    tools=["mcp__ctdpa__check_ctdpa_compliance"],
    maxTurns=3,
)


# ---------- Agent 4: Appeals Processor ----------

appeals_processor = AgentDefinition(
    description="Validates appeal procedures in business privacy policy and checks consumer request response timelines against CTDPA's 45-day limit.",
    prompt=APPEALS_PROCESSOR_PROMPT,
    model=AGENT_MODEL,
    tools=["mcp__ctdpa__validate_appeal_procedures"],
    maxTurns=3,
)


# ---------- Agent 5: Report Generator ----------

report_generator = AgentDefinition(
    description="Synthesizes all audit findings into a comprehensive report with risk scoring, violation details, and actionable recommendations.",
    prompt=REPORT_GENERATOR_PROMPT,
    model=AGENT_MODEL,
    tools=["mcp__ctdpa__generate_audit_report"],
    maxTurns=3,
)


# All agents as a dict (keyed by name for ClaudeAgentOptions.agents)
ALL_AGENTS = {
    "regulatory_analyst": regulatory_analyst,
    "data_forensics": data_forensics,
    "compliance_auditor": compliance_auditor,
    "appeals_processor": appeals_processor,
    "report_generator": report_generator,
}
