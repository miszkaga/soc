# SOC 2 Audit Automation Pipeline

An AI-powered pipeline that automates the creation of SOC 2 Type II audit documentation using GPT-4 Turbo and Retrieval-Augmented Generation (RAG).

## What It Does

Given a plain-text system description, the pipeline automatically:

1. **Phase 0 – Scope Assessment** (`scope_assessor.py`): Identifies subservice organizations (vendors) and classifies the reporting method (Carve-Out vs. Inclusive).
2. **Phase 1 – Control Generation** (`rcm_generator.py`): Generates SOC 2 controls aligned with the system description, injecting mandatory vendor monitoring controls for Carve-Out engagements.
3. **Phase 2 – Scope Validation** (`scope_validator.py`): Quality gate – uses semantic LLM analysis to verify that every required vendor has a monitoring control before proceeding.
4. **Phase 3 – Sanitization Pipeline**:
   - **3a – Sanitizer** (`automated_sanitizer.py`): Anonymizes sensitive organization/vendor names using AI-generated token substitution.
   - **3b – Mapper** (`modul_2_mapper_rag.py`): Maps each control to AICPA Trust Services Criteria (TSC) codes and Points of Focus using FAISS-backed RAG.
   - **3c – Auditor** (`auditor.py`): Generates AICPA-standard audit test procedures with evidence lists and sampling guidance.

**Final output**: `none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx` – a complete SOC 2 Type II audit procedures workbook.

## Architecture

```
System Description (text)
        │
        ▼
[Phase 0] scope_assessor.py   → scope_strategy.json
        │
        ▼
[Phase 1] rcm_generator.py    → controls.xlsx (RAW)
        │
        ▼
[Phase 2] scope_validator.py  → scope_validation_report.json
        │  ⚠️ Pipeline halts here if validation fails
        ▼
[Phase 3a] automated_sanitizer.py  → sanitized_controls.xlsx
        │
        ▼
[Phase 3b] modul_2_mapper_rag.py   → mapped_controls_rag.xlsx
        │
        ▼
[Phase 3c] auditor.py              → FINAL_SOC2_AUDIT_ENGLISH.xlsx
```

## Setup

### Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/miszkaga/soc.git
cd soc

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Edit .env and replace 'sk-...' with your actual OpenAI API key
```

### One-time Vector Index Setup

Before running the pipeline for the first time, build the FAISS knowledge base from the bundled AICPA PDF documents:

```bash
python prepare_vectors.py
```

This creates the `soc2_vector_index/` directory used by the RAG mapper in Phase 3b.

## Usage

### Full Pipeline (Recommended)

```bash
# 1. Place your system description in:
#    none_ex_files/system_description.txt

# 2. Run the orchestrator
python orchestrator.py
```

### Running Individual Phases

```bash
python scope_assessor.py      # Phase 0
python rcm_generator.py       # Phase 1
python scope_validator.py     # Phase 2
python automated_sanitizer.py # Phase 3a
python modul_2_mapper_rag.py  # Phase 3b
python auditor.py             # Phase 3c
```

## Output Files

All output files are written to the `none_ex_files/` directory:

| File | Phase | Description |
|---|---|---|
| `scope_strategy.json` | 0 | Vendor list, classification, required controls |
| `controls.xlsx` | 1 | Raw generated controls |
| `scope_validation_report.json` | 2 | Validation results per vendor |
| `sensitive_map.json` | 3a | Sanitization token mapping |
| `sanitized_controls.xlsx` | 3a | Anonymized controls |
| `mapped_controls_rag.xlsx` | 3b | Controls with TSC codes and Points of Focus |
| `FINAL_SOC2_AUDIT_ENGLISH.xlsx` | 3c | Final audit procedures workbook |

## Security

- **Never commit your `.env` file.** It is excluded by `.gitignore`.
- Use `.env.example` as a template; copy it to `.env` and fill in your real API key.
