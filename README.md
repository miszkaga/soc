# SOC 2 Audit Automation Pipeline

An AI-powered pipeline that automates the creation of SOC 2 Type II audit documentation using GPT-4 Turbo and Retrieval-Augmented Generation (RAG).

## Privacy-First Design

Real-world SOC 2 system descriptions contain sensitive information: legal entity names, vendor relationships, internal system names, employee roles, and data-centre locations. Sending this raw data to an external LLM API would create a data-sovereignty and confidentiality risk.

The pipeline therefore **sanitizes the system description algorithmically — without any API call — before a single token is sent to OpenAI**. Every downstream LLM phase works only with anonymous placeholders such as `[ORGANIZATION_1]` or `[VENDOR_2]`.

A **local LLM enrichment step (Phase 0.5)** then optionally adds short context labels to those placeholders (e.g. `[ORGANIZATION_1: Cloud infrastructure provider]`) using an on-premise Ollama instance — still without sending any data to an external server. This bridges the gap between full privacy and contextually rich controls.

### Sanitization Approach (Phase 0)

`system_description_sanitizer.py` uses two techniques, both entirely local:

1. **spaCy Named Entity Recognition (NER)** – detects organisations, persons, locations, and products using the `en_core_web_sm` model.
2. **Regex patterns** – catches structured artefacts: e-mail addresses, IP addresses, URLs, and phone numbers.

### Local Token Enrichment (Phase 0.5)

`phase_0_5_map_enricher.py` calls a locally running **Ollama** LLM to add a ≤5-word technical descriptor to each anonymisation token. **No data leaves your machine.**

| Before enrichment | After enrichment |
|---|---|
| `[ORGANIZATION_1]` | `[ORGANIZATION_1: Cloud infrastructure provider]` |
| `[ORGANIZATION_3]` | `[ORGANIZATION_3: Customer support ticketing tool]` |

**Quality trade-offs** compared to an LLM-based sanitizer:

| Aspect | Algorithmic (Phase 0) | Enriched (Phase 0.5) | LLM-based |
|---|---|---|---|
| Data privacy | ✅ Zero API exposure | ✅ Zero API exposure (local) | ❌ Sends raw text to API |
| Recall | ⚠️ May miss unusual proper nouns | ⚠️ May miss unusual proper nouns | ✅ Contextually aware |
| Vendor-specific controls | ⚠️ References `[ORGANIZATION_1]` | ✅ References `[ORGANIZATION_1: Cloud provider]` | ✅ Names the real vendor |
| Reproducibility | ✅ Deterministic | ⚠️ Varies by model | ⚠️ Varies by temperature |
| Requires extra software | ✅ No | ⚠️ Ollama (optional, graceful fallback) | ❌ OpenAI subscription |

Phase 0.5 degrades gracefully: if Ollama is not installed the pipeline continues with plain tokens.

## What It Does

Given a plain-text system description, the pipeline automatically:

1. **Phase 0 – System Description Sanitizer** (`system_description_sanitizer.py`): Algorithmically replaces all sensitive named entities with anonymous tokens. **No API call.** Produces `sanitized_system_description.txt` and `system_description_sensitive_map.json`.
2. **Phase 0.5 – Semantic Token Enrichment** (`phase_0_5_map_enricher.py`): Enriches blind tokens with short technical context labels using a **local Ollama LLM**. **No external API call.** Produces `enriched_sensitive_map.json` and updates `sanitized_system_description.txt`. *(Optional – pipeline continues without it.)*
3. **Phase 1 – Scope Assessment** (`scope_assessor.py`): Identifies subservice organisations (vendors) and classifies the reporting method (Carve-Out vs. Inclusive) — operating on the **sanitized/enriched** description. Loads the `vector_index_ssae21` FAISS index to inject authoritative SSAE 21 attestation-standards context (carve-out vs. inclusive definitions) directly into the LLM prompt. Falls back to prompt-only mode if the index is not present.
4. **Phase 2 – Control Generation** (`rcm_generator.py`): Generates SOC 2 controls aligned with the sanitized description, injecting mandatory vendor monitoring controls for Carve-Out engagements. Loads the `vector_index_tsc` FAISS index to inject official AICPA Trust Services Criteria (CC6, CC8, CC9 Points of Focus) into the LLM prompt, grounding generated controls in exact regulatory requirements. Falls back to prompt-only mode if the index is not present.
5. **Phase 3 – Scope Validation** (`scope_validator.py`): Quality gate — uses semantic LLM analysis to verify that every required vendor has a monitoring control before proceeding. Loads the `vector_index_ssae21` FAISS index to inject SSAE 21 audit-evidence requirements into the validation prompt, ensuring the quality check is anchored to authoritative standards. Falls back to prompt-only mode if the index is not present.
6. **Phase 4 – Audit Pipeline**:
   - **4.1 – Controls Sanitizer** (`automated_sanitizer.py`): Algorithmic safety-net pass that re-applies Phase 0 tokens to any control cell that might still carry a sensitive name. **No API call.**
   - **4.2 – Mapper** (`modul_2_mapper_rag.py`): Maps each control to AICPA Trust Services Criteria (TSC) codes and Points of Focus using FAISS-backed RAG.
   - **4.3 – Auditor** (`auditor.py`): Generates AICPA-standard audit test procedures with evidence lists and sampling guidance.
7. **Phase 5 – Report Re-hydrator** (`phase_5_rehydrator.py`): Reverses the token map and replaces all tokens in the final Excel workbook with the **original sensitive names**, producing the auditor-ready deliverable. **No API call.**

**Final output**: `none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx` — a complete SOC 2 Type II audit procedures workbook with real vendor names restored.

## Architecture

```
System Description (raw, sensitive)
        │
        ▼
[Phase 0] system_description_sanitizer.py  → sanitized_system_description.txt
          (spaCy NER + Regex – NO API)        system_description_sensitive_map.json
        │
        ▼
[Phase 0.5] phase_0_5_map_enricher.py     → sanitized_system_description.txt (enriched tokens)
            (Local Ollama – NO EXTERNAL API)  enriched_sensitive_map.json
            ⚠️ Graceful fallback if Ollama
            is not installed
        │
        │  ◄── sensitive data never crosses this boundary ──►
        │
        ▼
[Phase 1] scope_assessor.py    → scope_strategy.json
          (RAG: vector_index_ssae21 – SSAE 21 carve-out/inclusive definitions)
        │
        ▼
[Phase 2] rcm_generator.py     → controls.xlsx (RAW, already uses tokens)
          (RAG: vector_index_tsc – AICPA TSC control requirements & Points of Focus)
        │
        ▼
[Phase 3] scope_validator.py   → scope_validation_report.json
          (RAG: vector_index_ssae21 – SSAE 21 audit evidence requirements)
        │  ⚠️ Pipeline halts here if validation fails
        ▼
[Phase 4.1] automated_sanitizer.py  → sanitized_controls.xlsx (NO API)
        │
        ▼
[Phase 4.2] modul_2_mapper_rag.py   → mapped_controls_rag.xlsx
        │
        ▼
[Phase 4.3] auditor.py              → FINAL_SOC2_AUDIT_ENGLISH.xlsx
        │
        ▼
[Phase 5] phase_5_rehydrator.py     → READY_FOR_AUDITOR_ENGLISH.xlsx
          (Reverse token map – NO API)  (original names restored)
```

## Setup

### Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- *(Optional, recommended)* **Ollama** for local LLM token enrichment (Phase 0.5):
  - Install Ollama from <https://ollama.com>
  - Pull an 8B model before running the pipeline:
    ```bash
    ollama run llama3.1
    ```
  - The pipeline will auto-detect Ollama on `localhost:11434`. If it is not running,
    Phase 0.5 is silently skipped and the pipeline continues with plain anonymous tokens.

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

# 4. Download the spaCy language model used by the Phase 0 sanitizer
python -m spacy download en_core_web_sm
# If this step fails (e.g. offline environment), Phase 0 will automatically
# fall back to regex-only mode and will still sanitize structured artefacts
# (emails, IPs, URLs). Named-entity detection will be skipped.

# 5. Configure your API key
cp .env.example .env
# Edit .env and replace 'sk-...' with your actual OpenAI API key
```

### One-time Vector Index Setup

Before running the pipeline for the first time, build the FAISS knowledge base from the bundled AICPA PDF documents:

```bash
python prepare_vectors.py
```

This creates three FAISS vector index directories:
- `soc2_vector_index/` – legacy monolithic index used by Phase 4.2 (RAG mapper)
- `vector_index_ssae21/` – SSAE 21 attestation-standards index used by Phases 1 & 3
- `vector_index_tsc/` – AICPA Trust Services Criteria index used by Phase 2

PDFs are routed into the domain-specific indices automatically based on their filename:
PDFs containing `ssae`, `standards`, or `attestation` in the name → `vector_index_ssae21`;
PDFs containing `tsc`, `criteria`, or `trust` → `vector_index_tsc`.
All PDFs also contribute to the monolithic `soc2_vector_index`.

Place your AICPA PDF documents in `pdf_docs/` before running the script.

## Usage

### Full Pipeline (Recommended)

```bash
# 1. Place your system description in:
#    none_ex_files/system_description.txt

# 2. (Optional) Start Ollama for enriched token context labels:
#    ollama run llama3.1

# 3. Run the orchestrator
python orchestrator.py
```

### Running Individual Phases

```bash
python system_description_sanitizer.py  # Phase 0   – sanitize first (no API)
python phase_0_5_map_enricher.py        # Phase 0.5 – enrich tokens (local Ollama, optional)
python scope_assessor.py                # Phase 1
python rcm_generator.py                 # Phase 2
python scope_validator.py               # Phase 3
python automated_sanitizer.py           # Phase 4.1 (no API)
python modul_2_mapper_rag.py            # Phase 4.2
python auditor.py                       # Phase 4.3
python phase_5_rehydrator.py            # Phase 5   – restore real names (no API)
```

## Output Files

All output files are written to the `none_ex_files/` directory:

| File | Phase | Description |
|---|---|---|
| `system_description_sensitive_map.json` | 0 | Reverse-lookup map: original entity → token |
| `sanitized_system_description.txt` | 0 / 0.5 | Anonymised system description (safe to use with LLMs) |
| `enriched_sensitive_map.json` | 0.5 | Token map with Ollama context labels (original name → enriched token) |
| `scope_strategy.json` | 1 | Vendor list, classification, required controls |
| `controls.xlsx` | 2 | Raw generated controls (using anonymous tokens) |
| `scope_validation_report.json` | 3 | Validation results per vendor |
| `sensitive_map.json` | 4.1 | Final combined sanitization map |
| `sanitized_controls.xlsx` | 4.1 | Controls after safety-net pass |
| `mapped_controls_rag.xlsx` | 4.2 | Controls with TSC codes and Points of Focus |
| `FINAL_SOC2_AUDIT_ENGLISH.xlsx` | 4.3 | Final audit procedures workbook (anonymised) |
| `READY_FOR_AUDITOR_ENGLISH.xlsx` | 5 | Auditor-ready workbook with original names restored |

## Security

- **Never commit your `.env` file.** It is excluded by `.gitignore`.
- Use `.env.example` as a template; copy it to `.env` and fill in your real API key.
- The `system_description_sensitive_map.json` and `enriched_sensitive_map.json` files contain the original sensitive entity names. Treat them as confidential and do not share or commit them.
