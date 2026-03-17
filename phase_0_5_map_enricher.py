#!/usr/bin/env python3
"""
PHASE 0.5: Semantic Token Enrichment (Local LLM – No External API)
Enriches the blind anonymisation tokens produced by Phase 0 with short
technical context descriptors by calling a local Ollama instance.

Example transformation:
  Before:  [ORGANIZATION_1]
  After:   [ORGANIZATION_1: Cloud infrastructure provider]

WHY THIS EXISTS:
  Blind tokens like [ORGANIZATION_1] cause the downstream GPT-4 calls to
  produce generic controls that don't reflect the actual role of the vendor.
  Enriched tokens preserve privacy while giving the LLM just enough context
  to generate vendor-appropriate controls.

FALLBACK:
  If the Ollama server is unreachable the script copies the original map and
  sanitized text unchanged so that the pipeline can continue without enrichment.

INPUT FILES:
  none_ex_files/system_description_sensitive_map.json
  none_ex_files/sanitized_system_description.txt

OUTPUT FILES:
  none_ex_files/enriched_sensitive_map.json   (enriched token → original name)
  none_ex_files/sanitized_system_description.txt  (tokens replaced in-place)
"""

import sys
import json
import os
import re
import http.client
import urllib.parse
import time

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "llama3.1"  # falls back gracefully if unavailable

MAP_FILE = "none_ex_files/system_description_sensitive_map.json"
SANITIZED_FILE = "none_ex_files/sanitized_system_description.txt"
ENRICHED_MAP_FILE = "none_ex_files/enriched_sensitive_map.json"

# Maximum seconds to wait for a single Ollama request
OLLAMA_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Ollama interface
# ---------------------------------------------------------------------------

def _ollama_reachable() -> bool:
    """Return True if the Ollama server is listening."""
    try:
        conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=5)
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        conn.close()
        return resp.status == 200
    except Exception:
        return False


def _query_ollama(entity_name: str) -> str:
    """
    Ask the local Ollama model for a ≤5-word technical description of entity_name.
    Returns the trimmed response string, or "" on any failure.
    """
    # Strip characters that could interfere with the prompt structure
    safe_name = entity_name.replace("'", "").replace('"', "").replace("\n", " ").strip()
    prompt = (
        f"In 5 words or less, what is the technical or business function of "
        f"'{safe_name}' in an IT architecture? "
        f"Return only the short description, no conversational text."
    )
    payload = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    )
    try:
        conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
        conn.request(
            "POST",
            "/api/generate",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        conn.close()
        if resp.status != 200:
            return ""
        data = json.loads(raw)
        description = data.get("response", "").strip()
        # Strip any surrounding quotes the model might add
        description = description.strip('"\'')
        # Truncate to a reasonable length (avoid runaway responses)
        if len(description) > 60:
            description = description[:57].rstrip() + "..."
        return description
    except Exception as e:
        print(f"      ⚠️  Ollama error for '{entity_name}': {e}")
        return ""


# ---------------------------------------------------------------------------
# Enrichment logic
# ---------------------------------------------------------------------------

def _build_enriched_token(original_token: str, description: str) -> str:
    """
    Insert a description into a standard token.

    '[ORGANIZATION_1]'  +  'Cloud infrastructure provider'
    → '[ORGANIZATION_1: Cloud infrastructure provider]'
    """
    if not description:
        return original_token
    # Strip the closing ']' and append the description.
    return original_token.rstrip("]") + f": {description}]"


def enrich_map(sensitive_map: dict, use_ollama: bool) -> dict:
    """
    Return an *enriched* map:  original_name → enriched_token

    If use_ollama is False the original plain tokens are kept.
    """
    enriched: dict = {}
    total = len(sensitive_map)
    for idx, (original_name, plain_token) in enumerate(sensitive_map.items(), 1):
        print(f"  [{idx}/{total}] {original_name!r}", end="  →  ", flush=True)
        if use_ollama:
            description = _query_ollama(original_name)
            enriched_token = _build_enriched_token(plain_token, description)
        else:
            enriched_token = plain_token
            description = ""
        print(f"{enriched_token}")
        enriched[original_name] = enriched_token
        # Small back-off between requests to avoid flooding the local server
        if use_ollama and idx < total:
            time.sleep(0.2)
    return enriched


def apply_enriched_tokens(text: str, sensitive_map: dict, enriched_map: dict) -> str:
    """
    Replace every plain token in *text* with the corresponding enriched token.

    Processes longest original names first to prevent partial-string collisions.
    """
    # Build plain_token → enriched_token lookup
    plain_to_enriched: dict = {}
    for original_name, enriched_token in enriched_map.items():
        plain_token = sensitive_map.get(original_name)
        if plain_token and plain_token != enriched_token:
            plain_to_enriched[plain_token] = enriched_token

    # Replace longest plain tokens first
    for plain_token, enriched_token in sorted(
        plain_to_enriched.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        text = text.replace(plain_token, enriched_token)
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("PHASE 0.5: Semantic Token Enrichment (Local Ollama – No External API)")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 1. Load required input files
    # ------------------------------------------------------------------
    if not os.path.exists(MAP_FILE):
        print(f"❌  Sensitive map not found: {MAP_FILE}")
        print("    Run Phase 0 (system_description_sanitizer.py) first.")
        sys.exit(1)

    with open(MAP_FILE, encoding="utf-8") as f:
        sensitive_map: dict = json.load(f)

    if not os.path.exists(SANITIZED_FILE):
        print(f"❌  Sanitized description not found: {SANITIZED_FILE}")
        sys.exit(1)

    with open(SANITIZED_FILE, encoding="utf-8") as f:
        sanitized_text: str = f.read()

    print(f"✓ Loaded sensitive map ({len(sensitive_map)} entities)")
    print(f"✓ Loaded sanitized description ({len(sanitized_text)} characters)")

    # ------------------------------------------------------------------
    # 2. Check Ollama availability
    # ------------------------------------------------------------------
    print(f"\n🔍 Checking Ollama server at {OLLAMA_HOST}:{OLLAMA_PORT} …")
    use_ollama = _ollama_reachable()

    if use_ollama:
        print(f"✅  Ollama is reachable – will enrich tokens using '{OLLAMA_MODEL}'")
    else:
        print(
            "⚠️  Ollama server is unreachable.\n"
            "    Proceeding without enrichment (plain tokens will be preserved).\n"
            "    To enable enrichment: install Ollama (https://ollama.com) and run:\n"
            f"      ollama run {OLLAMA_MODEL}"
        )

    # ------------------------------------------------------------------
    # 3. Build enriched map
    # ------------------------------------------------------------------
    print(f"\n📝 Enriching {len(sensitive_map)} entities …\n")
    enriched_map = enrich_map(sensitive_map, use_ollama=use_ollama)

    # ------------------------------------------------------------------
    # 4. Update the sanitized description in-place
    # ------------------------------------------------------------------
    updated_text = apply_enriched_tokens(sanitized_text, sensitive_map, enriched_map)

    with open(SANITIZED_FILE, "w", encoding="utf-8") as f:
        f.write(updated_text)
    print(f"\n📄 Updated sanitized description → {SANITIZED_FILE}")

    # ------------------------------------------------------------------
    # 5. Save enriched map
    # ------------------------------------------------------------------
    with open(ENRICHED_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(enriched_map, f, indent=4, ensure_ascii=False)
    print(f"🗂️  Enriched map saved    → {ENRICHED_MAP_FILE}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    enriched_count = sum(
        1 for orig, tok in enriched_map.items()
        if ":" in tok
    )
    print(f"\n✅ Phase 0.5 complete.")
    if use_ollama:
        print(f"   {enriched_count}/{len(enriched_map)} tokens enriched with Ollama descriptions.")
    else:
        print("   Tokens kept as-is (Ollama not available – pipeline continues unaffected).")
    print("=" * 80)


if __name__ == "__main__":
    main()
