"""
CT Data Privacy Auditor - Main Entry Point & Pipeline

Runs 5 sequential steps, each with its own SDK client and direct MCP
tool access (no orchestrator middleman):
  1. Regulatory Analyst  - Parse CT law PDFs into structured rules
  2. Data Forensics      - Detect PII in business data
  3. Compliance Auditor  - Check policy vs. rules vs. detected PII
  4. Appeals Processor   - Validate appeal procedures & timelines
  5. Report Generator    - Compile everything into a final report

Usage (CLI):
    python -m src.main --policy <policy_file> --data <csv_file> [--request-log <csv_file>]

Usage (Streamlit):
    from src.main import run_audit
    result = asyncio.run(run_audit(...))
"""

import asyncio
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

# Ensure Claude CLI is on PATH for claude-agent-sdk
_CLAUDE_DIR = Path.home() / "AppData" / "Roaming" / "Claude" / "claude-code"
if str(_CLAUDE_DIR) not in os.environ.get("PATH", "") and _CLAUDE_DIR.exists():
    _versions = sorted(_CLAUDE_DIR.glob("*"), reverse=True)
    if _versions:
        os.environ["PATH"] = str(_versions[0]) + os.pathsep + os.environ.get("PATH", "")

from dotenv import load_dotenv

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)
from src.agents.definitions import AGENT_MODEL
from src.agents.prompts import (
    REGULATORY_ANALYST_PROMPT,
    DATA_FORENSICS_PROMPT,
    COMPLIANCE_AUDITOR_PROMPT,
    APPEALS_PROCESSOR_PROMPT,
    REPORT_GENERATOR_PROMPT,
)
from src.mcp_server import ctdpa_server


load_dotenv()


# ---------- Agent step names ----------

AGENT_STEPS = [
    "Regulatory Analyst",
    "Data Forensics",
    "Compliance Auditor",
    "Appeals Processor",
    "Report Generator",
]


# ---------- Find Claude CLI binary ----------

def _find_cli_path() -> str | None:
    _claude_code_dir = Path.home() / "AppData" / "Roaming" / "Claude" / "claude-code"
    if _claude_code_dir.exists():
        _versions = sorted(_claude_code_dir.glob("*"), reverse=True)
        if _versions:
            return str(_versions[0] / "claude.exe")
    return None


# ---------- Cost-tracking query helper ----------

async def run_agent_query(client: ClaudeSDKClient, prompt: str) -> tuple[str, dict]:
    """Send a query and collect the response text plus cost/usage data.

    Returns:
        (response_text, cost_info) where cost_info contains:
            input_tokens, output_tokens, total_cost_usd, duration_ms, num_turns
    """
    await client.query(prompt)

    response_text = ""
    cost_info = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost_usd": 0.0,
        "duration_ms": 0,
        "duration_api_ms": 0,
        "num_turns": 0,
    }

    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    response_text += block.text
                # Also capture any tool result content that the SDK
                # surfaces as a block with a .text attribute
                elif hasattr(block, "text") and isinstance(getattr(block, "text", None), str):
                    response_text += block.text
            # Accumulate token usage per assistant message
            if msg.usage:
                cost_info["input_tokens"] += msg.usage.get("input_tokens", 0)
                cost_info["output_tokens"] += msg.usage.get("output_tokens", 0)

        elif isinstance(msg, ResultMessage):
            # Capture final cost and timing
            cost_info["total_cost_usd"] = msg.total_cost_usd or 0.0
            cost_info["duration_ms"] = msg.duration_ms or 0
            cost_info["duration_api_ms"] = msg.duration_api_ms or 0
            cost_info["num_turns"] = msg.num_turns or 0
            # ResultMessage.usage may have total tokens too
            if msg.usage:
                if msg.usage.get("input_tokens"):
                    cost_info["input_tokens"] = msg.usage["input_tokens"]
                if msg.usage.get("output_tokens"):
                    cost_info["output_tokens"] = msg.usage["output_tokens"]
            break

    return response_text, cost_info


# ---------- Retry wrapper ----------

async def run_agent_query_with_retry(
    client: ClaudeSDKClient,
    prompt: str,
    agent_name: str,
    max_retries: int = 2,
) -> tuple[str, dict]:
    """Run an agent query with retries on invalid JSON responses.

    Retries up to max_retries times, adding stronger JSON enforcement
    on each retry. Accumulates costs across all attempts.
    """
    total_cost = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost_usd": 0.0,
        "duration_ms": 0,
        "duration_api_ms": 0,
        "num_turns": 0,
    }

    current_prompt = prompt
    last_text = ""

    for attempt in range(max_retries):
        text, cost = await run_agent_query(client, current_prompt)
        last_text = text

        # Accumulate costs across retries
        for key in ("input_tokens", "output_tokens", "num_turns"):
            total_cost[key] += cost.get(key, 0)
        total_cost["total_cost_usd"] += cost.get("total_cost_usd", 0.0)
        total_cost["duration_ms"] += cost.get("duration_ms", 0)
        total_cost["duration_api_ms"] += cost.get("duration_api_ms", 0)

        # Check if we got valid JSON
        try:
            extracted = extract_json_from_result(text)
            json.loads(extracted)
            return text, total_cost  # Valid JSON, success
        except (json.JSONDecodeError, TypeError):
            if attempt < max_retries - 1:
                current_prompt = (
                    f"RETRY (attempt {attempt + 2}/{max_retries}): {prompt}\n\n"
                    f"IMPORTANT: Your previous response was not valid JSON. "
                    f"Return ONLY the raw JSON from the tool call. "
                    f"No markdown, no explanation, no code fences."
                )

    return last_text, total_cost  # Return best effort after all retries


# ---------- JSON extraction ----------

def extract_json_from_result(result: str) -> str:
    """Extract JSON from an agent's response text."""
    # Try direct parse
    try:
        json.loads(result)
        return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Try code blocks
    json_blocks = re.findall(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", result or "")
    for block in json_blocks:
        try:
            json.loads(block.strip())
            return block.strip()
        except json.JSONDecodeError:
            continue

    # Try raw JSON object/array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = (result or "").find(start_char)
        if start != -1:
            depth = 0
            for i in range(start, len(result)):
                if result[i] == start_char:
                    depth += 1
                elif result[i] == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = result[start:i+1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            break

    return result or "{}"


# ---------- Per-step client helper ----------

async def run_step(
    system_prompt: str,
    query: str,
    step_name: str,
    cli_path: str | None,
    max_retries: int = 2,
) -> tuple[str, dict]:
    """Run a single pipeline step with its own isolated SDK client.

    Each step gets:
      - Its own fresh client (no accumulated context from prior steps)
      - The agent's specialized prompt as the system prompt
      - Direct access to the MCP tools (no subagent delegation)
      - max_turns=3 (call tool → return JSON → done)
    """
    options = ClaudeAgentOptions(
        model=AGENT_MODEL,
        system_prompt=system_prompt,
        mcp_servers={"ctdpa": ctdpa_server},
        permission_mode="bypassPermissions",
        max_turns=3,
        cli_path=cli_path,
    )

    client = ClaudeSDKClient(options=options)
    await client.connect()
    try:
        return await run_agent_query_with_retry(client, query, step_name, max_retries)
    finally:
        await client.disconnect()


# ---------- Main pipeline ----------

async def run_audit(
    policy_path: str,
    data_paths: list[str],
    request_log_path: str | None = None,
    pdf_directory: str | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict:
    """Run the complete 5-step CTDPA audit pipeline.

    Each step runs in its own SDK client with direct MCP tool access —
    no orchestrator middleman that can swallow JSON results.

    Args:
        policy_path: Path to the business privacy policy text file.
        data_paths: Paths to business data CSV files.
        request_log_path: Optional path to consumer request log CSV.
        pdf_directory: Path to CT law PDF directory.
        progress_callback: Optional fn(step_number, step_name) for UI updates.

    Returns:
        Dict with keys: report, agent_costs, total_cost, report_file
    """
    def progress(step: int, name: str):
        if progress_callback:
            progress_callback(step, name)

    # Resolve paths
    base_dir = Path(__file__).resolve().parent.parent
    if pdf_directory is None:
        pdf_directory = str(base_dir / "Data" / "real" / "policies" / "CT")

    policy_path = str(Path(policy_path).resolve())
    data_paths = [str(Path(p).resolve()) for p in data_paths]
    if request_log_path:
        request_log_path = str(Path(request_log_path).resolve())

    policy_text = Path(policy_path).read_text(encoding="utf-8")
    cli_path = _find_cli_path()
    agent_costs = []

    # --- Step 1: Regulatory Analyst ---
    progress(1, "Regulatory Analyst")
    step1_result, step1_cost = await run_step(
        system_prompt=REGULATORY_ANALYST_PROMPT,
        query=(
            f"Call the parse_ct_statutes tool with pdf_directory=\"{pdf_directory}\".\n\n"
            f"Return ONLY the raw JSON result from the tool. Nothing else."
        ),
        step_name="Regulatory Analyst",
        cli_path=cli_path,
    )
    ct_rules_json = extract_json_from_result(step1_result)
    agent_costs.append({"agent": "Regulatory Analyst", **step1_cost})

    # --- Step 2: Data Forensics ---
    progress(2, "Data Forensics")
    step2_result, step2_cost = await run_step(
        system_prompt=DATA_FORENSICS_PROMPT,
        query=(
            f"Call the detect_pii_in_data tool with csv_file_paths={json.dumps(data_paths)}.\n\n"
            f"Return ONLY the raw JSON result from the tool. Nothing else."
        ),
        step_name="Data Forensics",
        cli_path=cli_path,
    )
    pii_report_json = extract_json_from_result(step2_result)
    agent_costs.append({"agent": "Data Forensics", **step2_cost})

    # --- Step 3: Compliance Auditor ---
    progress(3, "Compliance Auditor")
    step3_result, step3_cost = await run_step(
        system_prompt=COMPLIANCE_AUDITOR_PROMPT,
        query=(
            f"Call the check_ctdpa_compliance tool with these parameters:\n"
            f"- business_policy: {json.dumps(policy_text)}\n"
            f"- ct_rules_json: {json.dumps(ct_rules_json)}\n"
            f"- pii_report_json: {json.dumps(pii_report_json)}\n\n"
            f"Return ONLY the raw JSON result from the tool. Nothing else."
        ),
        step_name="Compliance Auditor",
        cli_path=cli_path,
    )
    compliance_json = extract_json_from_result(step3_result)
    agent_costs.append({"agent": "Compliance Auditor", **step3_cost})

    # --- Step 4: Appeals Processor ---
    progress(4, "Appeals Processor")
    step4_result, step4_cost = await run_step(
        system_prompt=APPEALS_PROCESSOR_PROMPT,
        query=(
            f"Call the validate_appeal_procedures tool with these parameters:\n"
            f"- business_policy: {json.dumps(policy_text)}\n"
            f"- request_log_path: {json.dumps(request_log_path or '')}\n\n"
            f"Return ONLY the raw JSON result from the tool. Nothing else."
        ),
        step_name="Appeals Processor",
        cli_path=cli_path,
    )
    appeals_json = extract_json_from_result(step4_result)
    agent_costs.append({"agent": "Appeals Processor", **step4_cost})

    # --- Step 5: Report Generator ---
    progress(5, "Report Generator")
    output_dir = str(base_dir / "output")
    step5_result, step5_cost = await run_step(
        system_prompt=REPORT_GENERATOR_PROMPT,
        query=(
            f"Call the generate_audit_report tool with these parameters:\n"
            f"- ct_rules_json: {json.dumps(ct_rules_json)}\n"
            f"- pii_report_json: {json.dumps(pii_report_json)}\n"
            f"- compliance_report_json: {json.dumps(compliance_json)}\n"
            f"- appeals_json: {json.dumps(appeals_json)}\n"
            f"- output_dir: {json.dumps(output_dir)}\n\n"
            f"Return ONLY the raw JSON result from the tool. Nothing else."
        ),
        step_name="Report Generator",
        cli_path=cli_path,
    )
    report_json = extract_json_from_result(step5_result)
    agent_costs.append({"agent": "Report Generator", **step5_cost})

    # Save report
    output_path = base_dir / "output"
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_path / f"ctdpa_audit_report_{timestamp}.json"

    try:
        report = json.loads(report_json)
    except json.JSONDecodeError:
        report = {"raw_response": report_json}

    # Embed cost data into the saved report
    total_cost = sum(c["total_cost_usd"] for c in agent_costs)
    total_input = sum(c["input_tokens"] for c in agent_costs)
    total_output = sum(c["output_tokens"] for c in agent_costs)
    total_duration = sum(c["duration_ms"] for c in agent_costs)

    cost_summary = {
        "total_cost_usd": total_cost,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_duration_ms": total_duration,
        "model": AGENT_MODEL,
        "per_agent": agent_costs,
    }

    report["_cost_summary"] = cost_summary

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    return {
        "report": report,
        "agent_costs": agent_costs,
        "cost_summary": cost_summary,
        "report_file": str(report_file),
    }


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="CT Data Privacy Act (CTDPA) Compliance Auditor"
    )
    parser.add_argument("--policy", required=True, help="Path to privacy policy text file")
    parser.add_argument("--data", required=True, nargs="+", help="Path(s) to business data CSV(s)")
    parser.add_argument("--request-log", help="Optional path to consumer request log CSV")
    parser.add_argument("--pdf-dir", help="Path to CT law PDF directory (default: Data/CTLaw)")

    args = parser.parse_args()

    for path_arg, label in [(args.policy, "Policy"), *((d, "Data") for d in args.data)]:
        if not Path(path_arg).exists():
            print(f"Error: {label} file not found: {path_arg}")
            sys.exit(1)
    if args.request_log and not Path(args.request_log).exists():
        print(f"Error: Request log not found: {args.request_log}")
        sys.exit(1)

    def cli_progress(step, name):
        print(f"\n[{step}/5] Running {name}...")

    result = asyncio.run(run_audit(
        policy_path=args.policy,
        data_paths=args.data,
        request_log_path=args.request_log,
        pdf_directory=args.pdf_dir,
        progress_callback=cli_progress,
    ))

    cs = result["cost_summary"]
    print("\n" + "=" * 60)
    print("  AUDIT COMPLETE")
    print("=" * 60)
    report = result["report"]
    summary = report.get("executive_summary", {})
    if summary:
        status = summary.get("overall_compliance_status", summary.get("overall_status", "N/A"))
        print(f"  Status:     {status}")
        print(f"  Risk Grade: {summary.get('risk_grade', 'N/A')}")
        print(f"  Violations: {summary.get('total_violations', report.get('violations_summary', {}).get('total_violations', '?'))}")
    print(f"\n  Total Cost:   ${cs['total_cost_usd']:.4f}")
    print(f"  Total Tokens: {cs['total_tokens']:,}")
    print(f"  Duration:     {cs['total_duration_ms'] / 1000:.1f}s")
    print(f"\n  Report: {result['report_file']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
