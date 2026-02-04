"""
PHASE 2: SCOPE VALIDATOR (LLM EDITION)
Validates RAW controls against scope strategy using Semantic Analysis.

Why LLM?
- Handles synonyms ("AWS" == "Amazon Web Services").
- Understands context (Distinguishes between "We use AWS" and "We review AWS").
- More robust than Keyword Matching.
"""

import sys
import os
import json
import pandas as pd
from openai import OpenAI
from typing import Dict, List
from config import OPENAI_API_KEY, SOC2_MODEL

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

client = OpenAI(api_key=OPENAI_API_KEY)

# File paths
SCOPE_STRATEGY_FILE = "none_ex_files/scope_strategy.json"
CONTROLS_FILE = "none_ex_files/controls.xlsx"
OUTPUT_FILE = "none_ex_files/scope_validation_report.json"

def load_data():
    if not os.path.exists(SCOPE_STRATEGY_FILE):
        raise FileNotFoundError(f"Missing {SCOPE_STRATEGY_FILE}")
    if not os.path.exists(CONTROLS_FILE):
        raise FileNotFoundError(f"Missing {CONTROLS_FILE}")

    with open(SCOPE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
        strategy = json.load(f)

    df = pd.read_excel(CONTROLS_FILE)
    return strategy, df

def validate_with_llm(vendors: List[Dict], controls_text: str) -> Dict:
    """
    Asks the LLM to act as the Judge.
    """
    vendor_names = [v["vendor_name"] for v in vendors]

    prompt = f"""
    You are a SOC 2 Quality Assurance Auditor.
    
    TASK:
    Verify if the provided 'Control Matrix' contains specific monitoring controls for the required 'Vendors'.
    
    REQUIRED VENDORS (Must have a control):
    {json.dumps(vendor_names)}
    
    CONTROL MATRIX (Raw Text):
    {controls_text}
    
    CRITERIA:
    1. A valid control must explicitly mention the vendor (or a common alias, e.g., 'AWS' for 'Amazon Web Services').
    2. The control must describe a "Review", "Audit", "Monitoring", or "Assessment" of that vendor.
    3. Be strict. If the vendor is mentioned but not reviewed, it fails.
    
    OUTPUT JSON FORMAT:
    {{
      "overall_status": "PASS" or "FAIL",
      "results": [
        {{
          "vendor": "Vendor Name",
          "status": "PASS" or "FAIL",
          "matched_control_ref": "Ref ID or None",
          "reasoning": "Why it passed or failed"
        }}
      ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model=SOC2_MODEL,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ LLM Validation Error: {e}")
        return {"overall_status": "ERROR", "results": []}

def main():
    print("=" * 80)
    print("PHASE 2: SCOPE VALIDATOR (INTELLIGENT LLM)")
    print("=" * 80)

    # 1. Load Data
    try:
        strategy, df = load_data()
        print(f"✓ Loaded Strategy & {len(df)} Controls")
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # 2. Check Prerequisites
    classification = strategy.get("reporting_method", {}).get("classification", "")
    vendors = strategy.get("subservice_organizations", [])

    if classification != "CARVE_OUT" or not vendors:
        print("✓ Validation Skipped: Not a Carve-Out strategy.")
        return

    # 3. Prepare Data for LLM (Convert Excel to a readable string)
    # We strip it down to just Ref and Description to save tokens
    target_col = next((col for col in df.columns if 'description' in col.lower()), df.columns[1])
    simplified_controls = df[['Control Ref', target_col]].to_string(index=False)

    print(f"\n[AI Auditor is reviewing {len(vendors)} vendors against controls...]")

    # 4. Run LLM Validation
    validation_result = validate_with_llm(vendors, simplified_controls)

    # 5. Process Results
    status = validation_result.get("overall_status", "FAIL")
    print(f"\nVALIDATION STATUS: {status}")

    for res in validation_result.get("results", []):
        icon = "✅" if res['status'] == "PASS" else "❌"
        print(f"   {icon} {res['vendor']}: {res['reasoning']}")

    # 6. Save Report
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(validation_result, f, indent=2)

    # 7. Pipeline Gate
    if status != "PASS":
        print("\n⛔ PIPELINE HALTED: Missing critical vendor controls.")
        sys.exit(1)
    else:
        print("\n✅ QUALITY GATE PASSED. Proceeding...")

if __name__ == "__main__":
    main()