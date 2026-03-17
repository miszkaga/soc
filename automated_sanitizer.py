"""
CONTROLS SANITIZER (Algorithmic – No API Calls)

WHY THIS MODULE STILL EXISTS:
  Even though the system description was sanitized BEFORE any LLM call
  (Phase 0), the control-generation LLM might occasionally hallucinate real
  entity names, or the controls could reference names from the scope strategy.
  This module applies a final, API-free safety pass over the generated
  controls before they are forwarded to the Mapper and Auditor.

HOW IT WORKS:
  1. Load the sensitive-entity map produced by Phase 0
     (none_ex_files/system_description_sensitive_map.json).
  2. Apply those same token substitutions to every control description.
  3. Optionally apply the regex patterns for structured artefacts (e-mail,
     IP addresses, URLs, phone numbers) as a further safety net.
  4. Save the result as sanitized_controls.xlsx with a canonical
     "Sanitized Control Description" column used by downstream modules.

NOTE: In a correctly operating pipeline the controls were generated FROM the
sanitized description, so this pass will usually find nothing to replace.
It is kept as a defence-in-depth measure.
"""

import sys
import re
import pandas as pd
import json
import os
from typing import Dict, List, Tuple

sys.stdout.reconfigure(encoding='utf-8')

INPUT_FILE = "none_ex_files/controls.xlsx"
OUTPUT_FILE = "none_ex_files/sanitized_controls.xlsx"
PHASE0_MAP_FILE = "none_ex_files/system_description_sensitive_map.json"
RESIDUAL_MAP_FILE = "none_ex_files/sensitive_map.json"

# Regex patterns for structured artefacts not covered by Phase 0 map
REGEX_PATTERNS: List[Tuple[str, str]] = [
    ("EMAIL", r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    ("IP_ADDRESS", r'\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b'),
    ("URL", r'https?://[^\s<>"\']+'),
    ("URL", r'www\.[a-zA-Z0-9\-]+\.[^\s<>"\']+'),
    ("PHONE", r'\b(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b'),
]

_regex_counters: Dict[str, int] = {}

def _next_token(category: str) -> str:
    n = _regex_counters.get(category, 0) + 1
    _regex_counters[category] = n
    return f"[{category}_{n}]"


def smart_detect_column(df: pd.DataFrame) -> str:
    """Detect the primary control description column."""
    text_cols = df.select_dtypes(include=['object', 'string']).columns.tolist()
    best_col = None
    max_score = -100
    keywords = ['description', 'activity', 'control', 'narrative']

    for col in text_cols:
        score = 0
        if any(key in col.lower() for key in keywords):
            score += 50
        sample = df[col].dropna().astype(str).tolist()
        if sample:
            avg_len = sum(len(t) for t in sample) / len(sample)
            if avg_len > 30:
                score += avg_len * 0.5
        if score > max_score:
            max_score = score
            best_col = col
    return best_col


def apply_map(text: str, mapping: Dict[str, str]) -> str:
    """Apply token substitutions (longest keys first to avoid partial replacements)."""
    if not isinstance(text, str):
        return str(text)
    for phrase in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(phrase, mapping[phrase])
    return text


def apply_regex_safety_net(text: str, existing_tokens: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Apply regex patterns for structured artefacts not yet in the map."""
    if not isinstance(text, str):
        return str(text), existing_tokens
    for category, pattern in REGEX_PATTERNS:
        def replacer(m, cat=category):
            raw = m.group(0)
            if raw not in existing_tokens:
                existing_tokens[raw] = _next_token(cat)
            return existing_tokens[raw]
        text = re.sub(pattern, replacer, text)
    return text, existing_tokens


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"⚠️  {INPUT_FILE} not found – skipping sanitizer.")
        return

    print("=" * 80)
    print("CONTROLS SANITIZER (Algorithmic Safety Net – No API Calls)")
    print("=" * 80)

    df = pd.read_excel(INPUT_FILE)
    target_col = smart_detect_column(df)
    print(f"✓ Detected description column: '{target_col}'")

    # Load Phase 0 sensitive map (the source of truth for entity tokens)
    sensitive_map: Dict[str, str] = {}
    if os.path.exists(PHASE0_MAP_FILE):
        with open(PHASE0_MAP_FILE, 'r', encoding='utf-8') as f:
            sensitive_map = json.load(f)
        print(f"✓ Loaded {len(sensitive_map)} entity tokens from Phase 0 map")
    else:
        print(f"⚠️  Phase 0 map not found ({PHASE0_MAP_FILE}). Running regex-only pass.")

    replacements_found = 0

    def sanitize_cell(text: str) -> str:
        nonlocal replacements_found
        before = text if isinstance(text, str) else str(text)
        result = apply_map(before, sensitive_map)
        result, _ = apply_regex_safety_net(result, sensitive_map)
        if result != before:
            replacements_found += 1
        return result

    df['Sanitized Control Description'] = df[target_col].apply(sanitize_cell)

    # Persist the final (possibly augmented) map for audit trail
    with open(RESIDUAL_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(sensitive_map, f, indent=4, ensure_ascii=False)

    df.to_excel(OUTPUT_FILE, index=False)

    print(f"\n✅ Sanitized controls saved to: {OUTPUT_FILE}")
    if replacements_found == 0:
        print("   ℹ️  No residual sensitive data found – controls were already clean.")
    else:
        print(f"   ⚠️  {replacements_found} cell(s) had residual sensitive data replaced.")
    print("=" * 80)


if __name__ == "__main__":
    main()
