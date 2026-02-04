# SOC 2 Audit Automation

This repository contains automated tools for SOC 2 audit processes.

## Setup

### 1. Install Dependencies

```bash
pip install python-dotenv openai pandas openpyxl langchain langchain-community langchain-openai faiss-cpu
```

### 2. Configure Environment Variables

Create a `.env` file in the root directory with your OpenAI API key:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your actual API key
# OPENAI_API_KEY=your-api-key-here
```

**Important:** 
- Never commit the `.env` file to version control. It is already included in `.gitignore`.
- Use `.env.example` as a template for required environment variables.
- Keep your API keys secure and never share them publicly.

### 3. Environment Variable Loading

All scripts in this repository use a centralized environment variable loader located in `utils/env_loader.py`. This ensures consistent and secure handling of API keys and other secrets.

**Usage in your scripts:**

```python
from utils.env_loader import load_env, get_api_key

# Load environment variables from .env file
load_env()

# Get the OpenAI API key (validates that it exists)
api_key = get_api_key()
```

Alternatively, you can import from the config module:

```python
from config import OPENAI_API_KEY, SOC2_MODEL
```

## Available Scripts

- `module_1_scope_assessment.py` - SOC 2 scope assessment analysis
- `sanitazer/automated_sanitizer.py` - Sanitize control descriptions
- `sanitazer/prepare_vectors.py` - Prepare vector embeddings for RAG
- `sanitazer/modul_2_mapper_rag.py` - Map controls using RAG
- `sanitazer/auditor.py` - Generate audit procedures
- `sanitazer/rcm_generator.py` - Generate controls from system description

## Security Notes

- Never hardcode API keys in your code
- Always use the `.env` file for secrets
- The `.env` file is excluded from git via `.gitignore`
- All scripts use the centralized `utils/env_loader.py` for consistent secret management