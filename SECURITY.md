# Security Guidelines

## Environment Variables and Secrets Management

This repository uses a centralized approach for managing secrets and API keys.

### ✅ DO:

1. **Use the centralized utility for loading environment variables:**
   ```python
   from utils.env_loader import load_env, get_api_key
   
   load_env()
   api_key = get_api_key("OPENAI_API_KEY")
   ```

2. **Import from config modules:**
   ```python
   from config import OPENAI_API_KEY, SOC2_MODEL
   ```

3. **Keep secrets in .env file:**
   - Create a `.env` file in the root directory
   - Copy `.env.example` as a template
   - Add your actual API keys to `.env`
   - The `.env` file is already in `.gitignore`

### ❌ DON'T:

1. **Never hardcode API keys in source code:**
   ```python
   # BAD - Never do this!
   api_key = "sk-proj-..."
   ```

2. **Never commit .env file to git:**
   - The `.env` file is already in `.gitignore`
   - Always verify before committing: `git status`

3. **Never use direct os.getenv() in scripts:**
   ```python
   # BAD - Use the centralized utility instead
   import os
   api_key = os.getenv("OPENAI_API_KEY")
   ```

## Centralized Environment Loader

The repository provides a single utility module (`utils/env_loader.py`) that:

- ✅ Loads environment variables from `.env` file
- ✅ Validates that required secrets are present
- ✅ Provides clear error messages when keys are missing
- ✅ Centralizes all environment variable loading logic

## Reporting Security Issues

If you discover a security vulnerability, please report it by:

1. **Do NOT** open a public issue
2. Contact the repository maintainers privately
3. Include details about the vulnerability and how to reproduce it

## Checking for Hardcoded Secrets

Before committing, you can check for hardcoded secrets:

```bash
# Check for potential API keys
grep -r "sk-[A-Za-z0-9_-]\{20,\}" --include="*.py" .

# Verify .env is not tracked
git ls-files | grep ".env"
```

## Best Practices

1. **Rotate API keys regularly**
2. **Use different API keys for development and production**
3. **Never share API keys in chat, email, or documentation**
4. **Review .gitignore before committing**
5. **Use `.env.example` to document required environment variables**
