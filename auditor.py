import sys
import pandas as pd
from openai import OpenAI
import json
import os
import time
from config import OPENAI_API_KEY

sys.stdout.reconfigure(encoding='utf-8')


client = OpenAI(api_key=OPENAI_API_KEY)
INPUT_FILE = "none_ex_files/mapped_controls_rag.xlsx"
OUTPUT_FILE = "none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx"

def generate_audit_procedure(control_row):
    text = control_row.get("Sanitized Control", "")
    tsc = control_row.get("Mapped TSC", "")
    pof = control_row.get("Point of Focus", "")

    system_prompt = """
    You are a Senior CISA Auditor performing a SOC 2 Type 2 audit.
    Write a PRECISE AUDIT TEST PROCEDURE in English.

    INPUT: Control description + TSC Context + Point of Focus.

    REQUIREMENTS (SSAE 21):
    1. EVIDENCE LIST: List specific documents/screenshots. Must cover the PERIOD OF TIME (e.g., "Jan 1 - Dec 31").
    2. METHODS: Use Inspection, Observation, Reperformance.
    3. SAMPLING (CRITICAL):
       - If control is cyclical, DEFINE SAMPLE SIZE.
       - Language: "Obtain population of [X] for the audit period. Select a random sample of [Y] items."
       - AICPA Sizes: Daily (25-40), Weekly (5-10), Quarterly (2-4), Annual (1).

    Return JSON:
    {
      "evidence_list": ["1. Evidence Name...", "2. Evidence Name..."],
      "test_steps": [
        "1. [Inspection] Step description...",
        "2. [Sampling] Selection and verification details..."
      ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": f"CONTROL: {text}\nTSC: {tsc}\nPOINT OF FOCUS: {pof}"}],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)
    except: return {}

def main():
    if not os.path.exists(INPUT_FILE): return
    print("--- MODULE 3: AUDITOR (ENGLISH OUTPUT) ---")
    df = pd.read_excel(INPUT_FILE)

    final_data = []
    for idx, row in df.iterrows():
        print(f" -> Generating procedures for row {idx+1}...")
        plan = generate_audit_procedure(row)

        evidence = "\n".join([f"• {e}" for e in plan.get("evidence_list", [])])
        steps = "\n".join(plan.get("test_steps", []))

        final_data.append({
            "Control Ref": row.get("Control Ref"),
            "Control Description": row.get("Sanitized Control"),
            "SOC 2 Criteria": row.get("Mapped TSC"),
            "Point of Focus": row.get("Point of Focus"),
            "Evidence Required": evidence,
            "Test Procedures": steps
        })
        time.sleep(0.5)

    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        out_df = pd.DataFrame(final_data)
        out_df.to_excel(writer, index=False, sheet_name="Audit Plan")
        ws = writer.sheets["Audit Plan"]
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['E'].width = 50
        ws.column_dimensions['F'].width = 60

    print(f"✅ SUCCESS! Final English Audit Plan: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()