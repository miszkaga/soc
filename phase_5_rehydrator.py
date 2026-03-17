#!/usr/bin/env python3
"""
PHASE 5: Report Re-hydrator (Final Excel Restoration)
Replaces all anonymisation tokens in the final audit workbook with the
original sensitive names so that auditors receive a fully-named report.

INPUT FILES:
  none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx
  none_ex_files/enriched_sensitive_map.json   (falls back to sensitive_map.json)

OUTPUT FILE:
  none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx
"""

import sys
import json
import os
import re

sys.stdout.reconfigure(encoding="utf-8")

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    print("❌  openpyxl is required. Install it with: pip install openpyxl")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_XLSX = "none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx"

# Prefer the enriched map (Phase 0.5); fall back to the plain Phase 0 map.
ENRICHED_MAP_FILE = "none_ex_files/enriched_sensitive_map.json"
FALLBACK_MAP_FILE = "none_ex_files/system_description_sensitive_map.json"

OUTPUT_XLSX = "none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx"

# Column widths (column letter → width in characters)
COLUMN_WIDTHS: dict = {
    "A": 20,
    "B": 40,
    "C": 25,
    "D": 25,
    "E": 50,
    "F": 60,
    "G": 30,
}


# ---------------------------------------------------------------------------
# Token map helpers
# ---------------------------------------------------------------------------

def _load_token_map() -> dict:
    """
    Load the enriched (or plain) token map and return a reverse lookup:
      enriched_token → original_name

    Handles both enriched tokens ('[ORGANIZATION_1: Cloud provider]')
    and plain tokens ('[ORGANIZATION_1]').
    """
    map_file = ENRICHED_MAP_FILE if os.path.exists(ENRICHED_MAP_FILE) else FALLBACK_MAP_FILE

    if not os.path.exists(map_file):
        print(f"⚠️  No token map found (checked {ENRICHED_MAP_FILE} and {FALLBACK_MAP_FILE}).")
        print("    Proceeding without re-hydration – output will be a copy of the input.")
        return {}

    with open(map_file, encoding="utf-8") as f:
        forward_map: dict = json.load(f)

    print(f"✓ Loaded token map from {map_file} ({len(forward_map)} entries)")

    # Reverse: token → original name
    # Both enriched AND plain token variants point to the same original name
    # so that partial replacements (e.g. where Phase 0.5 was skipped) still work.
    reverse: dict = {}
    for original_name, token in forward_map.items():
        reverse[token] = original_name
        # Also index the plain-token version in case the xlsx was generated before
        # enrichment.
        plain = re.sub(r':\s*[^\]]+\]', ']', token)
        if plain != token:
            reverse.setdefault(plain, original_name)

    return reverse


# ---------------------------------------------------------------------------
# Re-hydration
# ---------------------------------------------------------------------------

def _rehydrate_cell_value(value, reverse_map: dict) -> str | None:
    """
    Replace all tokens in a single cell value.
    Returns the new string, or None if no replacement was made.
    """
    if not isinstance(value, str):
        return None
    new_value = value
    # Longest tokens first to avoid partial-match collisions
    for token, original in sorted(
        reverse_map.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if token in new_value:
            new_value = new_value.replace(token, original)
    return new_value if new_value != value else None


def rehydrate_workbook(wb: openpyxl.Workbook, reverse_map: dict) -> int:
    """
    Walk every cell in *wb* and replace tokens with original names.
    Returns the total number of substitutions made.
    """
    substitution_count = 0
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                new_val = _rehydrate_cell_value(cell.value, reverse_map)
                if new_val is not None:
                    cell.value = new_val
                    substitution_count += 1
    return substitution_count


def apply_column_widths(wb: openpyxl.Workbook, widths: dict):
    """Set column widths on every worksheet."""
    for sheet in wb.worksheets:
        for col_letter, width in widths.items():
            sheet.column_dimensions[col_letter].width = width


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("PHASE 5: Report Re-hydrator (Restore Original Names in Final Excel)")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 1. Validate inputs
    # ------------------------------------------------------------------
    if not os.path.exists(INPUT_XLSX):
        print(f"❌  Input workbook not found: {INPUT_XLSX}")
        print("    Run Phase 4 (auditor.py) first.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Build reverse token map
    # ------------------------------------------------------------------
    reverse_map = _load_token_map()

    # ------------------------------------------------------------------
    # 3. Load workbook
    # ------------------------------------------------------------------
    print(f"\n📂 Loading workbook: {INPUT_XLSX}")
    wb = openpyxl.load_workbook(INPUT_XLSX)
    sheet_names = wb.sheetnames
    print(f"   Sheets: {', '.join(sheet_names)}")

    # ------------------------------------------------------------------
    # 4. Re-hydrate
    # ------------------------------------------------------------------
    if reverse_map:
        print(f"\n🔄 Replacing {len(reverse_map)} token(s) across all cells …")
        count = rehydrate_workbook(wb, reverse_map)
        print(f"   {count} cell(s) updated.")
    else:
        print("\n⚠️  No tokens to replace – output is a copy of the input.")

    # ------------------------------------------------------------------
    # 5. Apply professional column widths
    # ------------------------------------------------------------------
    apply_column_widths(wb, COLUMN_WIDTHS)
    print("📐 Column widths applied.")

    # ------------------------------------------------------------------
    # 6. Save output
    # ------------------------------------------------------------------
    wb.save(OUTPUT_XLSX)
    print(f"\n✅ Phase 5 complete.")
    print(f"   Final auditor-ready report → {OUTPUT_XLSX}")
    print("=" * 80)


if __name__ == "__main__":
    main()
