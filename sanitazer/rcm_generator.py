import pandas as pd
from openai import OpenAI
import json
import os
from config import OPENAI_API_KEY, SOC2_MODEL


SYSTEM_DESC_FILE = "system_description.txt"
OUTPUT_FILE = "controls.xlsx"

def generate_controls_from_desc(description_text):
    """
    Generates SOC 2 controls that specifically align with the System Description.
    """
    system_prompt = """
    You are a SOC 2 Compliance Architect. 
    
    INPUT: A System Description (Section 3 of a SOC 2 report).
    
    TASK: Generate a list of realistic Internal Controls that support the claims in the description.
    
    RULES:
    1. If the description mentions specific tools (e.g., "Okta", "AWS", "GitHub"), the controls MUST name them.
    2. If the description makes specific commitments (e.g., "Daily backups at 02:00"), the controls MUST reflect that exact detail.
    3. Include controls for: 
       - Logical Access (Onboarding, Offboarding, Access Review)
       - Change Management (Code Review, Testing)
       - Operations (Backups, Monitoring)
       - Vendor Management (Review of subservice organizations mentioned in text)
    
    OUTPUT JSON FORMAT:
    {
      "controls": [
        {
          "Control Ref": "CC1.1-01",
          "Control Activity Description": "Full text of control...",
          "Frequency": "Daily/Weekly/Quarterly",
          "Owner": "Role Name"
        }
      ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"SYSTEM DESCRIPTION:\n{description_text}"}
            ],
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"API Error: {e}")
        return {"controls": []}

def main():
    print("--- GENERATOR: INTEGRATED MODE (ENGLISH) ---")

    # 1. Read System Description
    if not os.path.exists(SYSTEM_DESC_FILE):
        print(f"❌ Error: '{SYSTEM_DESC_FILE}' not found. Create it first.")
        return

    with open(SYSTEM_DESC_FILE, "r") as f:
        desc_text = f.read()

    print(f" -> Analyzing System Description ({len(desc_text)} chars)...")

    # 2. Generate Controls
    data = generate_controls_from_desc(desc_text)
    controls = data.get("controls", [])

    if not controls:
        print("❌ Failed to generate controls. Check API key or quota.")
        return

    # 3. Save to Excel
    df = pd.DataFrame(controls)
    df.to_excel(OUTPUT_FILE, index=False)

    print(f"✅ SUCCESS: Generated {len(controls)} aligned controls.")
    print(f"   Saved to: {OUTPUT_FILE}")
    print("   Example Control:")
    print(f"   Ref: {controls[0]['Control Ref']}")
    print(f"   Desc: {controls[0]['Control Activity Description']}")

if __name__ == "__main__":
    main()