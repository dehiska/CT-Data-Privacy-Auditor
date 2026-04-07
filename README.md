# CT Data Privacy Auditor

A multi-agent AI system that audits business compliance with the **Connecticut Data Privacy Act (CTDPA)** using Anthropic's Claude Agent SDK. Five specialized agents work in sequence to parse statutes, detect PII, check policy gaps, validate appeal procedures, and generate a comprehensive audit report -- all surfaced through an interactive Streamlit dashboard.

Built as a capstone project for the Generative AI course, Masters Spring 2026.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Agent Pipeline](#agent-pipeline)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Running the App](#running-the-app)
8. [Generating Sample Data](#generating-sample-data)
9. [Training the PII Model](#training-the-pii-model)
10. [How It Works](#how-it-works)
11. [Dashboard Features](#dashboard-features)
12. [Data Directories](#data-directories)
13. [Tech Stack](#tech-stack)

---

## Architecture

```
                          Streamlit Dashboard (app.py)
                                    |
                              run_audit()
                                    |
           +----------+----------+----------+----------+
           |          |          |          |          |
       Agent 1    Agent 2    Agent 3    Agent 4    Agent 5
      Regulatory   Data     Compliance  Appeals    Report
       Analyst   Forensics   Auditor   Processor  Generator
           |          |          |          |          |
           +----------+----------+----------+----------+
                                    |
                           MCP Server (5 tools)
                                    |
           +----------+----------+----------+----------+
           |          |          |          |          |
      parse_ct    detect_pii  check_ctdpa validate   generate
      statutes    in_data     compliance  appeal     audit
                                                     report
           |          |          |          |          |
       regulatory  forensics  compliance  appeals    report
          .py        .py        .py        .py        .py
```

Each agent runs in its own isolated SDK client with direct MCP tool access (no orchestrator middleman). This keeps responses focused and prevents context contamination between steps.

---

## Agent Pipeline

| Step | Agent | MCP Tool | Input | Output |
|------|-------|----------|-------|--------|
| 1 | **Regulatory Analyst** | `parse_ct_statutes` | CT law PDF directory | Structured rules JSON (thresholds, rights, exemptions, timelines) |
| 2 | **Data Forensics** | `detect_pii_in_data` | Business data CSVs | PII detection report (types, counts, confidence scores) |
| 3 | **Compliance Auditor** | `check_ctdpa_compliance` | Policy text + rules + PII report | Violation list with severity and similarity scores |
| 4 | **Appeals Processor** | `validate_appeal_procedures` | Policy text + request log CSV | Appeal procedure validation + timeline analysis |
| 5 | **Report Generator** | `generate_audit_report` | All prior results | Final audit report with risk grade, violations, recommendations |

Data flows forward: Step 3 receives output from Steps 1 and 2. Step 5 receives output from all prior steps.

---

## Project Structure

```
CT-Data-Privacy-Auditor/
|
|-- src/
|   |-- app.py                  # Streamlit dashboard (main UI)
|   |-- main.py                 # Pipeline orchestration (run_audit)
|   |-- mcp_server.py           # MCP server exposing 5 tools
|   |-- generate_dummy_data.py  # Sample data generator (Faker)
|   |
|   |-- agents/
|   |   |-- definitions.py      # AgentDefinition objects (model, tools, maxTurns)
|   |   |-- prompts.py          # System prompts for each agent
|   |
|   |-- tools/
|   |   |-- regulatory.py       # CT law PDF parser -> structured rules
|   |   |-- forensics.py        # PII detection (regex + keywords + ML)
|   |   |-- compliance.py       # Semantic similarity compliance checker
|   |   |-- appeals.py          # Appeal procedure + timeline validator
|   |   |-- report.py           # Final report synthesizer
|   |
|   |-- models/
|   |   |-- train_pii_model.py  # Train TF-IDF + LogisticRegression PII model
|   |
|   |-- utils/
|       |-- state.py            # Shared state utilities
|
|-- Data/
|   |-- sample/                 # Generated test data
|   |   |-- policies/           # Sample privacy policy texts
|   |   |-- business_data/      # Sample customer CSVs (36K records)
|   |   |-- request_logs/       # Sample consumer request logs (500 entries)
|   |
|   |-- real/
|       |-- policies/
|       |   |-- CT/             # 6 real CTDPA statute & enforcement PDFs
|       |   |-- Other_States/   # Placeholder for multi-state expansion
|       |-- business_data/      # Real CT business registry data
|       |-- request_logs/       # Real request logs (if available)
|
|-- Specs/                      # Agent specification documents
|-- models/                     # Trained ML model artifacts (.pkl)
|-- output/                     # Generated audit reports (JSON + MD)
|-- requirements.txt
|-- .gitignore
|-- README.md
```

---

## Prerequisites

- **Python 3.11+**
- **Claude Code CLI** installed (the Agent SDK shells out to it)
  - Install from: https://docs.anthropic.com/en/docs/claude-code
  - The app auto-detects it at `%APPDATA%\Claude\claude-code\<version>\claude.exe`
- **Anthropic API Key** with access to `claude-haiku-4-5-20251001` (or whichever model is configured in `src/agents/definitions.py`)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/dehiska/CT-Data-Privacy-Auditor.git
cd CT-Data-Privacy-Auditor

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Download the spaCy English model
python -m spacy download en_core_web_sm
```

---

## Configuration

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

The app loads this automatically via `python-dotenv`.

### Model Selection

The default model is `claude-haiku-4-5-20251001` (fast and cheap for development). To change it, edit the `AGENT_MODEL` variable in `src/agents/definitions.py`:

```python
AGENT_MODEL = "claude-haiku-4-5-20251001"  # Change to claude-sonnet-4-20250514 for better accuracy
```

---

## Running the App

### Streamlit Dashboard (recommended)

```bash
streamlit run src/app.py
```

The dashboard opens at `http://localhost:8501` and provides:
- Sidebar with data upload, jurisdiction toggle, and sample data option
- Animated progress bar during the 5-agent pipeline
- Interactive results with violation details, law citations, and human override buttons

### Command-Line Interface

```bash
python -m src.main \
    --policy Data/sample/policies/business_policy.txt \
    --data Data/sample/business_data/business_data.csv \
    --request-log Data/sample/request_logs/request_log.csv
```

Optional flags:
- `--pdf-dir <path>` -- Custom directory for CT law PDFs (default: `Data/real/policies/CT/`)

---

## Generating Sample Data

The project includes a Faker-based data generator that creates realistic CTDPA test data with intentional compliance violations:

```bash
python -m src.generate_dummy_data --records 36000 --requests 500 --output-dir Data/sample
```

| Flag | Default | Description |
|------|---------|-------------|
| `--records` | 36000 | Number of customer records to generate |
| `--requests` | 500 | Number of consumer request log entries |
| `--output-dir` | `sample_data` | Output directory for generated files |

**What gets generated:**

| File | Description | Intentional Violations |
|------|-------------|----------------------|
| `business_data.csv` | Customer records with PII (SSNs, health data, demographics) | ~60% have health data, ~30% racial/ethnic data, sensitive notes (biometric, neural, geolocation) |
| `request_log.csv` | Consumer rights request/response log | ~20% late responses (>45 days), ~5% extreme late (>90 days) |
| `business_policy.txt` | Privacy policy for a fictional company | Missing: delete, portability, opt-out, appeal rights |

All data uses Connecticut towns and ZIP codes. Randomization seed is `42` for reproducibility.

---

## Training the PII Model

The Data Forensics tool uses a TF-IDF + LogisticRegression model as one of three PII detection methods (alongside regex and keyword matching):

```bash
python -m src.models.train_pii_model
```

This generates synthetic training examples and saves the trained pipeline to `models/pii_model.pkl`. The model classifies text fragments into PII types (email, SSN, phone, health data, etc.).

---

## How It Works

### Pipeline Flow

1. **User uploads** a privacy policy, business data CSV, and optional request log via the Streamlit sidebar (or enables the CT jurisdiction toggle to auto-include CTDPA statute PDFs).

2. **`run_audit()`** in `src/main.py` runs 5 sequential steps. Each step creates a fresh `ClaudeSDKClient` with:
   - The agent's specialized system prompt
   - Direct access to the MCP tools (no orchestrator delegation)
   - `max_turns=3` (call tool, return JSON, done)
   - Retry logic (up to 2 attempts on JSON parse failure)

3. **MCP Server** (`src/mcp_server.py`) exposes 5 tools via the Model Context Protocol. Each tool wraps a Python module in `src/tools/` that does the actual computation.

4. **Results** are compiled into a structured JSON report, saved to `output/`, and rendered in the dashboard.

### Compliance Checking (Similarity Scoring)

The Compliance Auditor uses **sentence-transformers** (`all-MiniLM-L6-v2`) to compare the business policy against CTDPA right descriptions:

- The policy is split into **paragraphs** and each paragraph is compared against each right description
- The **best (max) similarity score** across paragraphs is used (avoids false positives from whole-document comparison)
- A **keyword fallback** catches paraphrased language the embedding model might miss
- Threshold: `0.45` per-paragraph similarity (or `0.25` + keyword match)

### PII Detection (Three-Pronged)

The Data Forensics tool uses three detection methods in parallel:

1. **Regex patterns** -- email, SSN, phone, date of birth
2. **CTDPA keyword matching** -- health conditions, biometric data, neural data, genetic data, geolocation, racial/ethnic origin, religious beliefs, sexual orientation
3. **ML model** -- TF-IDF + LogisticRegression trained on synthetic PII examples

No raw PII is ever stored or returned -- only detection metadata (types, counts, confidence scores).

---

## Dashboard Features

| Feature | Description |
|---------|-------------|
| **Executive Summary** | Compliance status (PASS/FAIL), risk grade (A-F), violation counts |
| **Violation Details** | Expandable cards with severity, confidence, CTDPA law citations, and remediation steps |
| **Human Override** | Button on each violation for a reviewer to mark as non-violation |
| **PII Findings** | Files analyzed, unique consumer count, PII types detected |
| **Cost Breakdown** | Per-agent token usage, cost (USD), and duration with Altair bar chart |
| **CT Jurisdiction Toggle** | Auto-includes 6 CTDPA statute/enforcement PDFs when enabled |
| **Report Downloads** | JSON report and Markdown executive summary |
| **Saved Reports** | Load previously generated reports from the output directory |
| **Progress Bar** | Animated progress showing which agent is currently running |

---

## Data Directories

| Directory | Contents | Tracked in Git? |
|-----------|----------|-----------------|
| `Data/sample/` | Generated test data (Faker) | Yes |
| `Data/real/policies/CT/` | 6 CTDPA statute and enforcement PDFs | Yes |
| `Data/real/business_data/` | Real CT business registry data | No |
| `output/` | Generated audit reports | No (`.gitignore`) |
| `models/` | Trained ML model artifacts | No (`.gitignore`) |

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Agent Framework | [Claude Agent SDK](https://docs.anthropic.com/en/docs/claude-code/sdk) | Multi-agent pipeline with MCP tool access |
| LLM | Claude Haiku 4.5 | Agent reasoning and tool invocation |
| Tool Protocol | [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) | Exposes Python tools to agents |
| Dashboard | [Streamlit](https://streamlit.io/) | Interactive web UI |
| NLP Similarity | [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`) | Semantic compliance checking |
| ML Pipeline | scikit-learn (TF-IDF + LogisticRegression) | PII classification |
| NLP Processing | spaCy (`en_core_web_sm`) | Text analysis |
| PDF Parsing | PyPDF2 | Extract text from CTDPA statute PDFs |
| Charts | Altair | Cost breakdown visualization |
| Data Generation | Faker | Reproducible sample data with seed 42 |

---

## License

This project was developed for academic purposes as part of a Masters-level Generative AI course.
