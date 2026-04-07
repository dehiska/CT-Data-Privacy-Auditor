"""
CT Data Privacy Auditor - Streamlit Dashboard

Launch:
    streamlit run src/app.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path so `from src.* import ...` works
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Ensure Claude CLI is on PATH for claude-agent-sdk
_CLAUDE_DIR = str(Path.home() / "AppData" / "Roaming" / "Claude" / "claude-code")
if _CLAUDE_DIR not in os.environ.get("PATH", ""):
    # Find the latest installed version
    _versions = sorted(Path(_CLAUDE_DIR).glob("*"), reverse=True) if Path(_CLAUDE_DIR).exists() else []
    if _versions:
        os.environ["PATH"] = str(_versions[0]) + os.pathsep + os.environ.get("PATH", "")

import altair as alt
import pandas as pd
import streamlit as st

# Must be first Streamlit call
st.set_page_config(
    page_title="CT Data Privacy Auditor",
    page_icon="shield",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "Data"
SAMPLE_DIR = DATA_DIR / "sample" / "policies"
SAMPLE_BIZ_DIR = DATA_DIR / "sample" / "business_data"
SAMPLE_LOG_DIR = DATA_DIR / "sample" / "request_logs"
REAL_POLICY_DIR = DATA_DIR / "real" / "policies"
REAL_BIZ_DIR = DATA_DIR / "real" / "business_data"
REAL_LOG_DIR = DATA_DIR / "real" / "request_logs"


# ================================================================
# Sidebar - File uploads & controls
# ================================================================

st.sidebar.title("Data Privacy Auditor")
st.sidebar.markdown("State-Level Compliance Audit System")
st.sidebar.divider()

# --- Jurisdiction selector ---
st.sidebar.subheader("Jurisdiction")
CT_LAW_DIR = DATA_DIR / "real" / "policies" / "CT"
use_ct_law = st.sidebar.toggle(
    "Connecticut (CT)",
    value=True,
    help="Auto-includes CT law PDFs from Data/real/policies/CT/. Turn off to upload your own policy files.",
)
# Future: add more state toggles here

st.sidebar.divider()

# --- File uploaders ---
st.sidebar.subheader("Upload Business Files")
if use_ct_law:
    st.sidebar.caption(
        "CT law PDFs are auto-loaded for rule extraction. "
        "Upload the **business policy** you want to audit for compliance, "
        "or leave blank to audit the CT law PDFs themselves."
    )
else:
    st.sidebar.caption(
        "Upload the **law / regulation** and the **business policy** to audit."
    )

uploaded_policies = st.sidebar.file_uploader(
    "Business Privacy Policy (.txt or .pdf) — optional if CT is on"
    if use_ct_law else "Privacy Policy (.txt or .pdf)",
    type=["txt", "pdf"], key="policy",
    accept_multiple_files=True,
    help="Upload a business privacy policy to audit. If CT is toggled on and nothing is uploaded, the CT law PDFs are used." if use_ct_law else None,
)
uploaded_data = st.sidebar.file_uploader(
    "Business Data (.csv)", type=["csv"], key="data"
)
uploaded_log = st.sidebar.file_uploader(
    "Request Log (.csv) - optional", type=["csv"], key="log"
)

use_sample = st.sidebar.checkbox("Use sample data instead", value=False)

st.sidebar.divider()

# --- Run button ---
run_clicked = st.sidebar.button("Run Audit", type="primary", width="stretch")

# --- Load previous report ---
st.sidebar.divider()
st.sidebar.subheader("Previous Reports")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
report_files = sorted(OUTPUT_DIR.glob("*.json"), reverse=True)
report_options = ["(none)"] + [f.name for f in report_files]
selected_report = st.sidebar.selectbox("Load a saved report", report_options)


# ================================================================
# Helper: run audit pipeline
# ================================================================

def run_pipeline(policy_path: str, data_paths: list[str], log_path: str | None):
    """Run the audit pipeline and return results."""
    import concurrent.futures
    from src.main import run_audit

    # Run in a separate thread with a ProactorEventLoop (Windows needs
    # this to spawn subprocesses via asyncio.create_subprocess_exec)
    def _run_in_thread():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(run_audit(
                policy_path=policy_path,
                data_paths=data_paths,
                request_log_path=log_path,
                progress_callback=None,  # can't update Streamlit UI from thread
            ))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_run_in_thread)
        result = future.result(timeout=900)  # 15-minute timeout

    return result


# ================================================================
# Determine what to display
# ================================================================

result_data = None

# --- Run new audit ---
if run_clicked:
    has_policy = use_sample or use_ct_law or uploaded_policies
    has_data = use_sample or uploaded_data
    has_files = has_policy and has_data

    if not has_files:
        if not has_policy:
            st.error("Please enable a jurisdiction toggle, upload policy files, or check 'Use sample data'.")
        elif not has_data:
            st.error("Please upload a business data CSV file, or check 'Use sample data'.")
    else:
        # Save uploaded files to temp dir (or use sample paths)
        if use_sample:
            policy_path = str(SAMPLE_DIR / "business_policy.txt")
            data_paths = [str(SAMPLE_BIZ_DIR / "business_data.csv")]
            log_path = str(SAMPLE_LOG_DIR / "request_log.csv")
        else:
            tmp = tempfile.mkdtemp(prefix="ctdpa_")
            policy_path = str(Path(tmp) / "policy.txt")

            from PyPDF2 import PdfReader
            import io

            # --- Build the policy text to audit ---
            policy_text_parts = []

            # If CT toggle is on and no separate policy uploaded,
            # use the CT law PDFs as the policy to audit.
            if use_ct_law and not uploaded_policies and CT_LAW_DIR.exists():
                for pdf_file in sorted(CT_LAW_DIR.glob("*.pdf")):
                    try:
                        reader = PdfReader(str(pdf_file))
                        policy_text_parts.append(
                            "\n".join(page.extract_text() or "" for page in reader.pages)
                        )
                    except Exception:
                        pass  # Skip unreadable PDFs

            # User-uploaded business policy (overrides CT law as policy)
            if uploaded_policies:
                for pf in uploaded_policies:
                    if pf.name.lower().endswith(".pdf"):
                        reader = PdfReader(io.BytesIO(pf.getvalue()))
                        policy_text_parts.append(
                            "\n".join(page.extract_text() or "" for page in reader.pages)
                        )
                    else:
                        policy_text_parts.append(pf.getvalue().decode("utf-8", errors="replace"))

            Path(policy_path).write_text(
                "\n\n--- Next Document ---\n\n".join(policy_text_parts), encoding="utf-8"
            )

            data_paths = [str(Path(tmp) / "data.csv")]
            Path(data_paths[0]).write_bytes(uploaded_data.getvalue())

            log_path = None
            if uploaded_log:
                log_path = str(Path(tmp) / "request_log.csv")
                Path(log_path).write_bytes(uploaded_log.getvalue())

        progress_placeholder = st.empty()
        with progress_placeholder.container():
            st.info(
                "Running 5-agent audit pipeline — this typically takes **8-12 minutes**.\n\n"
                "Agents: Regulatory Analyst → Data Forensics → Compliance Auditor → Appeals Processor → Report Generator"
            )
            progress_bar = st.progress(0, text="Starting pipeline...")
        try:
            import time as _time, threading as _threading

            # Animate the progress bar while the pipeline runs
            _done_event = _threading.Event()

            def _animate_progress():
                import logging
                # Suppress noisy "missing ScriptRunContext" warnings from
                # background-thread Streamlit widget updates.
                logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)

                steps = [
                    (0.05, "1/5 Regulatory Analyst — parsing CT law PDFs..."),
                    (0.20, "2/5 Data Forensics — scanning for PII..."),
                    (0.40, "3/5 Compliance Auditor — checking policy gaps..."),
                    (0.60, "4/5 Appeals Processor — validating timelines..."),
                    (0.80, "5/5 Report Generator — compiling findings..."),
                ]
                idx = 0
                while not _done_event.is_set():
                    # Move to the next label based on elapsed time
                    elapsed = _time.monotonic() - _t0
                    if idx < len(steps) - 1 and elapsed > (idx + 1) * 120:
                        idx += 1
                    frac, label = steps[idx]
                    # Slowly creep within each phase
                    phase_extra = min(0.14, (elapsed - idx * 120) / 900)
                    try:
                        progress_bar.progress(min(frac + phase_extra, 0.95), text=label)
                    except Exception:
                        pass
                    _done_event.wait(3)

            _t0 = _time.monotonic()
            _anim = _threading.Thread(target=_animate_progress, daemon=True)
            _anim.start()

            result_data = run_pipeline(policy_path, data_paths, log_path)
            _done_event.set()
            progress_bar.progress(1.0, text="Audit complete!")
            st.session_state["last_result"] = result_data
        except Exception as e:
            _done_event.set()
            import traceback
            st.error(f"Pipeline error: {e}")
            st.code(traceback.format_exc(), language="text")

# --- Load previous report ---
elif selected_report != "(none)":
    report_path = OUTPUT_DIR / selected_report
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        cost_summary = report.get("_cost_summary", {
            "total_cost_usd": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_duration_ms": 0,
            "model": "unknown",
            "per_agent": [],
        })
        result_data = {
            "report": report,
            "agent_costs": cost_summary.get("per_agent", []),
            "cost_summary": cost_summary,
            "report_file": str(report_path),
        }
    except Exception as e:
        st.error(f"Error loading report: {e}")

# --- Or use last result from session ---
elif "last_result" in st.session_state:
    result_data = st.session_state["last_result"]


# ================================================================
# Render Dashboard
# ================================================================

if result_data is None:
    # Landing page
    st.title("Connecticut Data Privacy Act (CTDPA) Compliance Auditor")
    st.markdown("""
    ### Multi-Agent AI Audit System

    This system uses **5 specialized AI agents** to audit business compliance with the
    Connecticut Data Privacy Act:

    | Agent | Role |
    |-------|------|
    | **Regulatory Analyst** | Parses CT law PDFs into structured rules |
    | **Data Forensics** | Detects PII using regex + keywords + ML |
    | **Compliance Auditor** | Semantic similarity policy vs. law comparison |
    | **Appeals Processor** | Validates appeal procedures & timelines |
    | **Report Generator** | Compiles final audit report |

    **Get started:** Upload your files in the sidebar or check "Use sample data", then click **Run Audit**.
    """)
    st.stop()

if result_data is None:
    sys.exit(0)

report = result_data["report"]
cost_summary = result_data["cost_summary"]
agent_costs = result_data["agent_costs"]

# ── Normalize report: if agents returned narrative text instead of structured
# JSON, extract key fields from the raw_response markdown.
def _normalize_report(rpt: dict) -> dict:
    """Ensure the report has structured keys the dashboard can render."""
    import re as _re

    # Already has structured data? Nothing to do.
    if rpt.get("executive_summary") and rpt.get("violations"):
        return rpt

    # Handle error/failed reports
    if rpt.get("status") == "FAILED" or rpt.get("error"):
        rpt.setdefault("executive_summary", {
            "overall_compliance_status": "ERROR",
            "risk_grade": "?",
            "summary": f"Pipeline error: {rpt.get('error', 'Unknown error')}. {rpt.get('message', '')}",
        })
        rpt["_raw_markdown"] = f"## Pipeline Error\n\n**{rpt.get('error', '')}**\n\n{rpt.get('message', '')}\n\n**Root cause:** {rpt.get('root_cause', 'Unknown')}\n\n**Recommendation:** {rpt.get('recommendation', '')}"
        return rpt

    raw = rpt.get("raw_response", "")
    if not raw:
        return rpt

    upper = raw.upper()

    # --- Executive Summary ---
    if "NON-COMPLIANT" in upper or "NON_COMPLIANT" in upper:
        status = "NON_COMPLIANT"
    elif "COMPLIANT" in upper:
        status = "COMPLIANT"
    else:
        status = "UNKNOWN"

    grade_match = _re.search(r"(?:Risk Grade|Grade)[:\s]*\*{0,2}\s*\*{0,2}([A-F])", raw, _re.IGNORECASE)
    grade = grade_match.group(1).upper() if grade_match else "?"

    rpt.setdefault("executive_summary", {
        "overall_compliance_status": status,
        "risk_grade": grade,
        "summary": "",
    })

    # Extract summary paragraph (first paragraph after EXECUTIVE SUMMARY heading)
    summary_match = _re.search(
        r"(?:EXECUTIVE SUMMARY|SUMMARY)\s*\n+(.*?)(?:\n\n|\n---|\n###)", raw, _re.IGNORECASE | _re.DOTALL
    )
    if summary_match:
        rpt["executive_summary"]["summary"] = summary_match.group(1).strip().replace("*", "")

    # --- Violations ---
    violations = []
    # Find VIOLATION sections
    viol_pattern = _re.compile(
        r"VIOLATION\s*(\d+)[:\s]*(.*?)(?:\n\n|\Z)",
        _re.IGNORECASE | _re.DOTALL,
    )
    for m in viol_pattern.finditer(raw):
        title = m.group(2).strip().split("\n")[0].replace("*", "").strip()
        severity = "CRITICAL" if "CRITICAL" in title.upper() else "HIGH" if "HIGH" in title.upper() else "MEDIUM"
        violations.append({
            "type": title,
            "severity": severity,
            "finding": m.group(2).strip().replace("*", ""),
        })
    if violations:
        rpt.setdefault("violations", violations)
        rpt.setdefault("violations_summary", {
            "total_violations": len(violations),
            "critical_violations": sum(1 for v in violations if v["severity"] == "CRITICAL"),
            "high_violations": sum(1 for v in violations if v["severity"] == "HIGH"),
            "medium_violations": sum(1 for v in violations if v["severity"] == "MEDIUM"),
        })

    # --- Clean up raw markdown for display ---
    # Ensure each phase/checkmark gets its own line
    import re as _re2
    cleaned = _re2.sub(r'([✅❌⬜✓✗☑☒])\s*(Phase\s)', r'\1\n\n\2', raw)
    cleaned = _re2.sub(r'(\s)([✅❌])\s+(Phase\s)', r'\n\n\2 \3', cleaned)

    # Strip agent "Would you like to:" interactive prompts (no buttons exist)
    cleaned = _re2.sub(
        r"\n*---\n*\*{0,2}The audit framework.*$",
        "", cleaned, flags=_re2.DOTALL,
    )
    cleaned = _re2.sub(
        r"\n*Would you like to:.*$",
        "", cleaned, flags=_re2.DOTALL,
    )

    rpt["_raw_markdown"] = cleaned.rstrip()
    return rpt


report = _normalize_report(report)

st.title("CTDPA Compliance Audit Results")

tab_results, tab_eval = st.tabs(["Audit Results", "Evaluation"])

with tab_results:

    # ================================================================
    # Section 1: Budget Metrics (top row)
    # ================================================================

    st.header("Budget & Performance", divider="gray")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Cost",
            f"${cost_summary.get('total_cost_usd', 0):.4f}",
        )
    with col2:
        total_tokens = cost_summary.get("total_tokens", 0)
        st.metric(
            "Total Tokens",
            f"{total_tokens:,}" if total_tokens else "N/A",
        )
    with col3:
        duration_ms = cost_summary.get("total_duration_ms", 0)
        st.metric(
            "Total Duration",
            f"{duration_ms / 1000:.1f}s" if duration_ms else "N/A",
        )
    with col4:
        st.metric(
            "Model",
            cost_summary.get("model", "N/A"),
        )


    # --- Per-agent breakdown ---
    if agent_costs:
        with st.expander("Per-Agent Cost Breakdown", expanded=True):
            cost_df = pd.DataFrame(agent_costs)

            # Display table
            display_df = cost_df[["agent", "input_tokens", "output_tokens", "total_cost_usd", "duration_ms"]].copy()
            display_df.columns = ["Agent", "Input Tokens", "Output Tokens", "Cost (USD)", "Duration (ms)"]
            display_df["Cost (USD)"] = display_df["Cost (USD)"].apply(lambda x: f"${x:.4f}")
            display_df["Duration (ms)"] = display_df["Duration (ms)"].apply(lambda x: f"{x:,}")
            display_df["Input Tokens"] = display_df["Input Tokens"].apply(lambda x: f"{x:,}")
            display_df["Output Tokens"] = display_df["Output Tokens"].apply(lambda x: f"{x:,}")
            st.dataframe(display_df, width="stretch", hide_index=True)

            # Bar chart of cost per agent (Altair for proper axis control)
            chart_df = cost_df[["agent", "total_cost_usd"]].copy()
            chart_df.columns = ["Agent", "Cost (USD)"]
            max_cost = chart_df["Cost (USD)"].max()
            chart = alt.Chart(chart_df).mark_bar().encode(
                x=alt.X("Cost (USD):Q",
                         scale=alt.Scale(domain=[0, max_cost * 1.15 if max_cost > 0 else 1]),
                         title="Cost (USD)",
                         axis=alt.Axis(format="$.4f")),
                y=alt.Y("Agent:N", sort="-x", title=""),
                color=alt.Color("Agent:N", legend=alt.Legend(title="Agent")),
                tooltip=["Agent:N", alt.Tooltip("Cost (USD):Q", format="$.4f")],
            ).properties(height=220)
            st.altair_chart(chart, use_container_width=True)


    # ================================================================
    # Section 2: Executive Summary
    # ================================================================

    st.header("Executive Summary", divider="gray")

    exec_summary = report.get("executive_summary", {})
    # Handle both report formats
    status = exec_summary.get("overall_compliance_status", exec_summary.get("overall_status", "UNKNOWN"))
    risk_grade = exec_summary.get("risk_grade", exec_summary.get("risk_assessment", {}).get("grade", "?"))
    risk_level = exec_summary.get("risk_level", exec_summary.get("risk_assessment", {}).get("label", ""))
    compliance_pct = exec_summary.get("compliance_percentage", None)

    col_status, col_grade, col_pct = st.columns(3)

    with col_status:
        if "NON" in str(status).upper() or "FAIL" in str(status).upper():
            st.error(f"### {status}")
        elif "COMPLIANT" in str(status).upper() or "PASS" in str(status).upper():
            st.success(f"### {status}")
        else:
            st.warning(f"### {status}")

    with col_grade:
        grade_colors = {"A": "success", "B": "success", "C": "warning", "D": "error", "F": "error"}
        method = getattr(st, grade_colors.get(str(risk_grade), "info"))
        method(f"### Risk Grade: {risk_grade}")

    with col_pct:
        if compliance_pct is not None:
            st.metric("Compliance", f"{compliance_pct}%")
        else:
            st.metric("Compliance", "N/A")

    # Summary text
    summary_text = exec_summary.get("summary", "")
    if summary_text:
        st.info(summary_text)

    # Violation counts
    violations_summary = report.get("violations_summary", {})
    if not violations_summary:
        # Try alternate structure
        violations_summary = exec_summary

    v_total = violations_summary.get("total_violations", 0)
    v_critical = violations_summary.get("critical_violations", violations_summary.get("critical", 0))
    v_high = violations_summary.get("high_violations", violations_summary.get("high", 0))
    v_medium = violations_summary.get("medium_violations", violations_summary.get("medium", 0))

    if v_total:
        vcol1, vcol2, vcol3, vcol4 = st.columns(4)
        vcol1.metric("Total Violations", v_total)
        vcol2.metric("Critical", v_critical)
        vcol3.metric("High", v_high)
        vcol4.metric("Medium", v_medium)


    # ================================================================
    # Section 3: Violations Detail
    # ================================================================

    violations = report.get("detailed_violations", report.get("violations", []))
    recommendations = report.get("recommendations", [])
    reg_analysis = report.get("regulatory_analysis", {})
    ct_rules = reg_analysis.get("applicable_rules", reg_analysis)

    # Map CTDPA section references for common violation types
    CTDPA_SECTIONS = {
        "access": {
            "section": "Sec. 42-520(a)(1)",
            "quote": "A controller shall... confirm whether or not the controller is processing the consumer's personal data and provide the consumer access to such personal data.",
        },
        "correct": {
            "section": "Sec. 42-520(a)(2)",
            "quote": "A controller shall... correct inaccuracies in the consumer's personal data, taking into account the nature of the personal data and the purposes of the processing.",
        },
        "delete": {
            "section": "Sec. 42-520(a)(3)",
            "quote": "A controller shall... delete personal data provided by, or obtained about, the consumer.",
        },
        "portability": {
            "section": "Sec. 42-520(a)(4)",
            "quote": "A controller shall... provide a copy of the consumer's personal data... in a portable and, to the extent technically feasible, readily usable format.",
        },
        "opt-out": {
            "section": "Sec. 42-520(a)(5)",
            "quote": "A controller shall... opt out of the processing of the personal data for purposes of targeted advertising, the sale of personal data, or profiling.",
        },
        "appeal": {
            "section": "Sec. 42-520(a)(6)",
            "quote": "A controller shall establish a process for a consumer to appeal the controller's refusal to take action on a request... The appeal process shall be conspicuously available.",
        },
        "UNDISCLOSED_SENSITIVE_DATA": {
            "section": "Sec. 42-515(27) & Sec. 42-520(b)",
            "quote": "A controller shall not process sensitive data concerning a consumer without obtaining the consumer's consent... 'Sensitive data' includes personal data revealing racial or ethnic origin, religious beliefs, health condition or diagnosis, sex life, sexual orientation, or biometric or genetic data.",
        },
        "THRESHOLD_TRIGGERED": {
            "section": "Sec. 42-516(a)",
            "quote": "This chapter applies to persons that conduct business in Connecticut or produce products or services targeted to residents of Connecticut and that during the preceding calendar year controlled or processed personal data of not less than 100,000 consumers... or 25,000 consumers and derived more than 25% of gross revenue from the sale of personal data.",
        },
        "LATE_RESPONSE": {
            "section": "Sec. 42-520(c)",
            "quote": "A controller shall act on a verified consumer request without undue delay, but not later than forty-five days after receipt of the request.",
        },
        "EXTREME_LATE_RESPONSE": {
            "section": "Sec. 42-520(c)",
            "quote": "A controller shall act on a verified consumer request without undue delay, but not later than forty-five days after receipt of the request.",
        },
    }

    if violations:
        st.header("Violation Details", divider="gray")
        overridden_count = sum(1 for i in range(len(violations)) if st.session_state.get(f"override_{i}", False))
        if overridden_count:
            st.caption(f"{len(violations)} violation(s) identified  |  {overridden_count} overridden by reviewer  |  **{len(violations) - overridden_count} active**")
        else:
            st.caption(f"{len(violations)} violation(s) identified")

        for i, v in enumerate(violations):
            severity = v.get("severity", v.get("priority", "MEDIUM"))
            v_type = v.get("type", "VIOLATION")
            right = v.get("right", "")
            data_cat = v.get("data_category", "")
            title = f"{v_type}" + (f" - {right}" if right else "") + (f" ({data_cat})" if data_cat else "")

            # Color-code by severity
            if severity == "CRITICAL":
                icon = "🔴"
            elif severity == "HIGH":
                icon = "🟠"
            elif severity == "MEDIUM":
                icon = "🟡"
            else:
                icon = "🔵"

            with st.expander(f"{icon} [{severity}] {title}", expanded=(severity == "CRITICAL")):
                # --- Metadata row ---
                mcol1, mcol2, mcol3 = st.columns(3)
                mcol1.write(f"**Severity:** {severity}")
                confidence = v.get("confidence", "")
                if confidence:
                    mcol2.write(f"**Confidence:** {confidence:.0%}" if isinstance(confidence, float) else f"**Confidence:** {confidence}")
                sim_score = v.get("similarity_score", "")
                if sim_score:
                    mcol3.write(f"**Similarity Score:** {sim_score}")

                # --- Finding / Description ---
                finding = v.get("finding", v.get("description", ""))
                if finding:
                    st.write(f"**Finding:** {finding}")

                # --- CTDPA Law Quote ---
                # Look up the section reference
                section_key = right if right else v_type
                law_ref = CTDPA_SECTIONS.get(section_key, {})
                section = v.get("ctdpa_section", law_ref.get("section", ""))
                quote = law_ref.get("quote", "")

                if section:
                    st.write(f"**CTDPA Section:** {section}")
                if quote:
                    st.info(f"**Law Text:** *\"{quote}\"*")

                # --- Matching recommendation ---
                matching_recs = [
                    r for r in recommendations
                    if r.get("for_violation") == v_type
                    and (not right or r.get("right", "") == right)
                ]
                if matching_recs:
                    rec = matching_recs[0]
                    st.success(f"**Recommended Action ({rec.get('priority', severity)}):** {rec.get('recommendation', '')}")
                else:
                    # Fallback to inline remediation
                    remediation = v.get("remediation", v.get("recommendation", ""))
                    if remediation:
                        st.success(f"**Remediation:** {remediation}")

                # --- Source file (for sensitive data violations) ---
                source = v.get("source_file", "")
                if source:
                    st.write(f"**Source File:** `{source}`")

                # --- Human override ---
                override_key = f"override_{i}"
                if override_key not in st.session_state:
                    st.session_state[override_key] = False

                st.divider()
                ocol1, ocol2 = st.columns([3, 1])
                if st.session_state[override_key]:
                    ocol1.success("Overridden by human reviewer - marked as non-violation")
                    if ocol2.button("Undo Override", key=f"undo_{i}", type="secondary"):
                        st.session_state[override_key] = False
                        st.rerun()
                else:
                    ocol1.caption("Does a human reviewer disagree with this finding?")
                    if ocol2.button("Override Violation", key=f"btn_override_{i}", type="primary"):
                        st.session_state[override_key] = True
                        st.rerun()


    # ================================================================
    # Section 4: PII Findings
    # ================================================================

    pii_findings = report.get("pii_detection_findings", report.get("pii_findings", {}))
    if pii_findings:
        st.header("PII Detection Findings", divider="gray")

        # Summary metrics
        files_analyzed = pii_findings.get("files_analyzed", 0)
        total_consumers = pii_findings.get("total_unique_consumers", 0)
        pii_types = pii_findings.get("pii_types_detected", [])

        if files_analyzed or total_consumers:
            pcol1, pcol2, pcol3 = st.columns(3)
            pcol1.metric("Files Analyzed", files_analyzed)
            pcol2.metric("Unique Consumers", f"{total_consumers:,}" if total_consumers else "N/A")
            pcol3.metric("PII Types Found", len(pii_types) if pii_types else "N/A")

        # Per-file details (from forensics.py output format)
        details = pii_findings.get("details", [])
        if details:
            for file_result in details:
                if "error" in file_result:
                    st.error(f"**{file_result.get('file', 'Unknown')}:** {file_result['error']}")
                    continue

                fname = file_result.get("file", "Unknown")
                rows = file_result.get("rows", "?")
                cols = file_result.get("columns", "?")
                avg_conf = file_result.get("average_confidence", 0)

                with st.expander(f"**{fname}** ({rows:,} rows, {cols} columns) — Avg Confidence: {avg_conf:.1%}"):
                    det_details = file_result.get("detection_details", [])
                    if det_details:
                        det_rows = []
                        for d in det_details:
                            det_rows.append({
                                "Type": d.get("type", "").replace("_", " ").title(),
                                "Method": d.get("method", ""),
                                "Confidence": f"{d.get('confidence', 0):.0%}",
                                "Count": d.get("count", "—"),
                            })
                        st.dataframe(pd.DataFrame(det_rows), width="stretch", hide_index=True)

                    col_pii = file_result.get("column_pii_indicators", [])
                    if col_pii:
                        st.write("**Column-Level PII Indicators:**")
                        for cp in col_pii:
                            st.write(f"- `{cp.get('column', '')}` → likely {cp.get('likely_pii_type', '')}")

        # Fallback: old format with pii_detected dict
        pii_detected = pii_findings.get("pii_detected", {})
        if pii_detected and isinstance(pii_detected, dict):
            st.subheader("Standard PII Detected")
            pii_rows = []
            for pii_type, info in pii_detected.items():
                if isinstance(info, dict):
                    pii_rows.append({
                        "Type": pii_type.replace("_", " ").title(),
                        "Count": info.get("count", "?"),
                        "Confidence": f"{info.get('confidence', '?')}",
                    })
            if pii_rows:
                st.dataframe(pd.DataFrame(pii_rows), width="stretch", hide_index=True)


    # ================================================================
    # Section 5: Appeals & Timeline
    # ================================================================

    appeals = report.get("appeals_analysis", report.get("appeals_findings", {}))
    if appeals:
        st.header("Appeals & Timeline Analysis", divider="gray")

        appeal_status = appeals.get("appeal_procedure_status", appeals.get("appeal_procedure", {}))
        if appeal_status:
            has_appeal = appeal_status.get("has_procedure", appeal_status.get("has_appeal", False))
            quality = appeal_status.get("quality", "UNKNOWN")
            if not has_appeal:
                st.error(f"Appeal Procedure: **MISSING** -- {appeal_status.get('ctdpa_requirement', '')}")
            else:
                st.success(f"Appeal Procedure: **Present** (Quality: {quality})")

        timeline = appeals.get("consumer_request_performance", appeals.get("timeline_analysis", {}))
        if timeline and "error" not in timeline:
            tcol1, tcol2, tcol3 = st.columns(3)
            tcol1.metric("Total Requests", timeline.get("total_requests", timeline.get("total_requests_analyzed", "?")))

            tl_comp = timeline.get("timeline_compliance", timeline)
            tcol2.metric("On Time", f"{100 - tl_comp.get('late_percentage', 0):.1f}%")
            tcol3.metric("Late Responses", tl_comp.get("late_responses", "?"))


    # ================================================================
    # Section 6: Downloads
    # ================================================================

    st.header("Download Reports", divider="gray")

    dcol1, dcol2 = st.columns(2)

    with dcol1:
        report_json_str = json.dumps(report, indent=2, default=str)
        st.download_button(
            "Download JSON Report",
            data=report_json_str,
            file_name="ctdpa_audit_report.json",
            mime="application/json",
            width="stretch",
        )

    with dcol2:
        # Use raw markdown from agent response, or saved executive summary file
        raw_md = report.get("_raw_markdown", "")
        md_files = list(OUTPUT_DIR.glob("*Executive_Summary*.md"))
        if raw_md:
            st.download_button(
                "Download Executive Summary (.md)",
                data=raw_md,
                file_name="CTDPA_Executive_Summary.md",
                mime="text/markdown",
                width="stretch",
            )
        elif md_files:
            md_content = md_files[0].read_text(encoding="utf-8")
            st.download_button(
                "Download Executive Summary (.md)",
                data=md_content,
                file_name="CTDPA_Executive_Summary.md",
                mime="text/markdown",
                width="stretch",
            )
        else:
            st.download_button(
                "Download Report as Text",
                data=report_json_str,
                file_name="ctdpa_audit_report.txt",
                mime="text/plain",
                width="stretch",
            )


    # ================================================================
    # Section 7: Full Audit Report
    # ================================================================

    raw_md = report.get("_raw_markdown", "")
    if raw_md:
        st.header("Full Audit Report", divider="gray")
        st.markdown(raw_md)


# ================================================================
# EVALUATION TAB
# ================================================================

with tab_eval:
    st.header("Agent Evaluation", divider="gray")
    st.caption("Evaluate agent accuracy using Ragas (LLM-based) and custom metrics (ground truth comparison).")

    # --- Ground truth source ---
    gt_source = st.radio(
        "Ground Truth Source",
        ["Sample (built-in)", "Upload JSON", "None (Ragas only)"],
        horizontal=True,
        help="'Sample' uses the built-in ACME test data ground truth. 'Upload' lets you provide your own. 'None' runs Ragas metrics only.",
    )

    ground_truth = None

    if gt_source == "Sample (built-in)":
        from src.evaluation.ground_truth import SAMPLE_GROUND_TRUTH
        ground_truth = SAMPLE_GROUND_TRUTH
        st.info("Using built-in ground truth for the ACME sample dataset (from `generate_dummy_data.py`).")

    elif gt_source == "Upload JSON":
        gt_file = st.file_uploader("Upload ground truth JSON", type=["json"], key="gt_upload")
        if gt_file:
            try:
                ground_truth = json.loads(gt_file.getvalue().decode("utf-8"))
                from src.evaluation.ground_truth import validate_ground_truth
                valid, msg = validate_ground_truth(ground_truth)
                if valid:
                    st.success(f"Ground truth loaded ({len(ground_truth.get('expected_violations', []))} expected violations)")
                else:
                    st.error(f"Invalid ground truth: {msg}")
                    ground_truth = None
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    else:
        st.warning("No ground truth selected. Only Ragas LLM-based metrics will be available (faithfulness, relevance, context precision).")

    # --- Run Evaluation button ---
    eval_clicked = st.button("Run Evaluation", type="primary", key="run_eval")

    if eval_clicked:
        with st.spinner("Running evaluation metrics..."):
            try:
                from src.evaluation.evaluate_agents import evaluate_audit
                eval_results = evaluate_audit(report, ground_truth)
                st.session_state["eval_results"] = eval_results
            except Exception as e:
                import traceback
                st.error(f"Evaluation error: {e}")
                st.code(traceback.format_exc(), language="text")

    # --- Display results ---
    eval_results = st.session_state.get("eval_results")

    if eval_results:

        # ---- A. Custom Metrics (require ground truth) ----
        custom = eval_results.get("custom_metrics")
        if custom:
            st.subheader("Custom Metrics (Ground Truth Comparison)")

            cm1, cm2, cm3 = st.columns(3)

            # Violation Detection Accuracy
            va = custom.get("violation_accuracy", {})
            with cm1:
                acc = va.get("accuracy", 0)
                color = "normal" if acc >= 0.7 else "off"
                st.metric("Violation Detection Accuracy", f"{acc:.0%}", delta=None)
                st.caption(f"TP: {va.get('true_positives', 0)}  FP: {va.get('false_positives', 0)}  FN: {va.get('false_negatives', 0)}  TN: {va.get('true_negatives', 0)}")

            # PII Precision / Recall
            pii = custom.get("pii_detection", {})
            with cm2:
                f1 = pii.get("f1", 0)
                st.metric("PII Detection F1", f"{f1:.0%}")
                st.caption(f"Precision: {pii.get('precision', 0):.0%}  |  Recall: {pii.get('recall', 0):.0%}")

            # Policy Compliance Score
            pc = custom.get("policy_compliance", {})
            with cm3:
                score = pc.get("score", 0)
                st.metric("Policy Compliance Score", f"{score:.0%}")
                st.caption(f"{pc.get('correct', 0)} / {pc.get('total', 6)} rights correctly classified")

            # --- Detailed breakdowns ---
            with st.expander("Violation Detection Details"):
                st.write("**Detected violations:**")
                for v in va.get("detected", []):
                    st.write(f"  - {v}")
                st.write("**Expected violations:**")
                for v in va.get("expected", []):
                    st.write(f"  - {v}")

            with st.expander("PII Detection Details"):
                pcol1, pcol2 = st.columns(2)
                with pcol1:
                    st.write("**Detected PII types:**")
                    for t in pii.get("detected", []):
                        marker = "+" if t not in pii.get("extra", []) else "+  (extra)"
                        st.write(f"  {marker} {t}")
                with pcol2:
                    st.write("**Expected PII types:**")
                    for t in pii.get("expected", []):
                        marker = "-  (missed)" if t in pii.get("missed", []) else "+"
                        st.write(f"  {marker} {t}")

            with st.expander("Per-Right Compliance Breakdown"):
                per_right = pc.get("per_right", {})
                if per_right:
                    right_rows = []
                    for right, info in per_right.items():
                        right_rows.append({
                            "Right": right.title(),
                            "Expected": "Covered" if info["expected_covered"] else "Missing",
                            "Detected": "Flagged as Missing" if info["detected_missing"] else "Not Flagged",
                            "Result": "Correct" if info["correct"] else "INCORRECT",
                        })
                    st.dataframe(pd.DataFrame(right_rows), width="stretch", hide_index=True)

        elif eval_results.get("has_ground_truth") is False:
            st.info("Custom metrics require ground truth data. Select 'Sample (built-in)' or upload a ground truth JSON to see violation accuracy, PII precision/recall, and policy compliance scores.")

        # ---- B. Ragas Metrics (LLM-based) ----
        ragas = eval_results.get("ragas_metrics")
        st.subheader("Ragas Metrics (LLM-Based)")

        if ragas and "error" not in ragas:
            rm1, rm2, rm3 = st.columns(3)

            with rm1:
                faith = ragas.get("faithfulness", 0)
                st.metric("Faithfulness", f"{faith:.0%}")
                st.caption("Do findings align with input data?")

            with rm2:
                rel = ragas.get("answer_relevance", 0)
                st.metric("Answer Relevance", f"{rel:.0%}")
                st.caption("Are findings relevant to the audit task?")

            with rm3:
                cp = ragas.get("context_precision", 0)
                st.metric("Context Precision", f"{cp:.0%}")
                st.caption("Did agents use the right context?")

            with st.expander("Interpretation Guide"):
                st.markdown("""
**Score Interpretation:**
- **0.8 - 1.0**: Excellent — agent outputs are highly accurate and relevant
- **0.6 - 0.8**: Good — minor issues, outputs are mostly reliable
- **0.4 - 0.6**: Fair — some inaccuracies, review recommended
- **0.0 - 0.4**: Poor — significant issues, agent outputs unreliable

**Metric Definitions:**
- **Faithfulness**: Measures if the compliance report's claims are supported by the input data (policy text, PII data, rules)
- **Answer Relevance**: Measures if the audit findings actually address the CTDPA compliance question
- **Context Precision**: Measures if the agents selected the correct pieces of evidence (policy clauses, PII types) for their conclusions
                """)

        elif ragas and "error" in ragas:
            st.warning(f"Ragas metrics unavailable: {ragas['error']}")
        else:
            st.info("Ragas metrics require the `ragas` and `langchain-anthropic` packages. Install with: `pip install ragas langchain-anthropic`")

        # ---- C. Per-Agent Breakdown ----
        per_agent = eval_results.get("per_agent", {})
        if per_agent:
            st.subheader("Per-Agent Evaluation")

            for agent_name, metrics in per_agent.items():
                status = metrics.get("status", "UNKNOWN")
                icon = {"PASS": "white_check_mark", "NEEDS_IMPROVEMENT": "warning", "PARTIAL": "large_orange_diamond", "NOT_EVALUATED": "black_circle"}.get(status, "question")
                with st.expander(f":{icon}: **{agent_name}** — {status}"):
                    for key, value in metrics.items():
                        if key == "status":
                            continue
                        if isinstance(value, float):
                            st.write(f"**{key.replace('_', ' ').title()}:** {value:.0%}")
                        else:
                            st.write(f"**{key.replace('_', ' ').title()}:** {value}")

        # ---- D. Download Evaluation Report ----
        st.divider()
        eval_json = json.dumps(eval_results, indent=2, default=str)
        st.download_button(
            "Download Evaluation Report (JSON)",
            data=eval_json,
            file_name="ctdpa_evaluation_report.json",
            mime="application/json",
        )

    elif not eval_clicked:
        st.info("Click **Run Evaluation** to assess agent accuracy against ground truth.")
