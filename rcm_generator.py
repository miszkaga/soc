import pandas as pd
from openai import OpenAI
import json
import os
from config import OPENAI_API_KEY, SOC2_MODEL
import sys
import rag_utils

sys.stdout.reconfigure(encoding='utf-8')

# Initialize client
client = OpenAI(api_key=OPENAI_API_KEY)

_SANITIZED_DESC_FILE = "none_ex_files/sanitized_system_description.txt"
_ORIGINAL_DESC_FILE = "none_ex_files/system_description.txt"
SCOPE_STRATEGY_FILE = "none_ex_files/scope_strategy.json"
OUTPUT_FILE = "none_ex_files/controls.xlsx"

# Attempt to load the TSC domain vector index once at module level.
# Falls back gracefully when the index has not yet been built.
_TSC_INDEX_NAME = "vector_index_tsc"
_kb_tsc = None
try:
    _kb_tsc = rag_utils.load_specific_knowledge_base(_TSC_INDEX_NAME)
    print(f"✓ RAG: Loaded '{_TSC_INDEX_NAME}' knowledge base for Phase 2.")
except FileNotFoundError:
    print(
        f"⚠️  RAG: '{_TSC_INDEX_NAME}' index not found. "
        f"Run prepare_vectors.py to enable authoritative TSC context. "
        f"Falling back to prompt-only mode."
    )

def load_scope_strategy():
    """Load scope strategy from Phase 0 if it exists."""
    try:
        with open(SCOPE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def generate_controls_from_desc(description_text, scope_strategy=None):
    """
    Generates SOC 2 controls that specifically align with the System Description.
    NOW SCOPE-AWARE: If scope_strategy is provided, generates required vendor controls.
    RAG-ENHANCED: Injects authoritative AICPA TSC context when the index is available.
    """
    
    # Base system prompt
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

    # RAG: retrieve authoritative TSC guidance when the index is available.
    if _kb_tsc is not None:
        try:
            is_carveout = (
                scope_strategy is not None
                and scope_strategy.get("reporting_method", {}).get("classification") == "CARVE_OUT"
            )
            rag_query = (
                "Requirements and points of focus for Logical Access CC6, Change Management CC8"
            )
            if is_carveout:
                rag_query += ", and Subservice Organization Vendor Monitoring CC9.2"

            rag_context = rag_utils.get_phase_context(_kb_tsc, rag_query, k=5)
            system_prompt += f"""

    OFFICIAL AICPA TRUST SERVICES CRITERIA TO ENFORCE:
    {rag_context}

    Generate controls that align exactly with the criteria provided above.
    """
        except Exception as rag_err:
            print(f"⚠️  RAG query failed (non-fatal): {rag_err}")
    
    # SCOPE-AWARE ENHANCEMENT: Add vendor-specific requirements
    if scope_strategy:
        classification = scope_strategy.get("reporting_method", {}).get("classification")
        vendors = scope_strategy.get("subservice_organizations", [])
        required_controls = scope_strategy.get("required_controls", [])
        
        if classification == "CARVE_OUT" and vendors:
            vendor_names = [v["vendor_name"] for v in vendors]
            vendor_list = ", ".join(vendor_names)
            
            system_prompt += f"""

    ⚠️ CRITICAL SCOPE REQUIREMENT (CARVE-OUT METHOD DETECTED):
    The system uses the CARVE-OUT method for the following subservice organizations: {vendor_list}
    
    You MUST generate the following MANDATORY controls:
    """
            
            for req in required_controls:
                vendor = req.get("vendor_name")
                system_prompt += f"""
    - Control Ref: CC9.2-{vendor.upper().replace(' ', '_')}
      Control Activity Description: "On an annual basis, the Security Team reviews the SOC 2 Type II report for {vendor} to ensure the subservice organization maintains adequate controls. Any exceptions or qualifications identified in the report are documented and escalated to management for remediation tracking."
      Frequency: Annual
      Owner: Security Team
      TSC Criteria: CC9.2
    """
            
            system_prompt += """
    
    These vendor monitoring controls are MANDATORY under SSAE 21 for carve-out method.
    Generate these controls EXACTLY as specified above, using the exact vendor names.
    """

    try:
        response = client.chat.completions.create(
            model=SOC2_MODEL,
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
    print("=" * 80)
    print("PHASE 2: CONTROL GENERATOR (Scope-Aware Mode)")
    print("=" * 80)

    # 1. Check for scope strategy from Phase 1
    print("\n[1/4] Checking for scope strategy from Phase 1...")
    scope_strategy = load_scope_strategy()

    if scope_strategy:
        classification = scope_strategy.get("reporting_method", {}).get("classification", "UNKNOWN")
        vendors = scope_strategy.get("subservice_organizations", [])
        print(f"✓ Scope strategy loaded: {classification} method")
        print(f"   Vendors identified: {len(vendors)}")
        for v in vendors:
            print(f"   - {v['vendor_name']}: {v['service_provided']}")
    else:
        print("⚠️  No scope strategy found. Running in generic mode.")
        print("   Recommendation: Run scope_assessor.py first for intelligent control generation.")

    # 2. Read System Description – resolve path at runtime
    system_desc_file = (
        _SANITIZED_DESC_FILE
        if os.path.exists(_SANITIZED_DESC_FILE)
        else _ORIGINAL_DESC_FILE
    )
    print(f"\n[2/4] Reading system description...")
    if not os.path.exists(system_desc_file):
        print(f"❌ Error: '{system_desc_file}' not found. Create it first.")
        return

    with open(system_desc_file, "r", encoding='utf-8') as f:
        desc_text = f.read()

    if os.path.exists(_SANITIZED_DESC_FILE):
        print(f"✓ Using SANITIZED system description ({len(desc_text)} characters)")
    else:
        print(f"✓ Loaded {len(desc_text)} characters (⚠️  not sanitized)")

    # 3. Generate Controls (scope-aware)
    print(f"\n[3/4] Generating controls...")
    if scope_strategy:
        print("   Mode: SCOPE-AWARE (will inject required vendor controls)")
    else:
        print("   Mode: GENERIC (basic controls only)")
    
    data = generate_controls_from_desc(desc_text, scope_strategy)
    controls = data.get("controls", [])

    if not controls:
        print("❌ Failed to generate controls. Check API key or quota.")
        return

    # 4. Save to Excel
    print(f"\n[4/4] Saving controls...")
    df = pd.DataFrame(controls)
    df.to_excel(OUTPUT_FILE, index=False)

    print(f"\n✓ Generated {len(controls)} controls")
    print(f"✓ Saved to: {OUTPUT_FILE}")
    
    # Show vendor controls if generated
    if scope_strategy and scope_strategy.get("reporting_method", {}).get("classification") == "CARVE_OUT":
        vendor_controls = [c for c in controls if "CC9.2" in c.get("Control Ref", "")]    
        print(f"\n📋 Vendor Monitoring Controls Generated: {len(vendor_controls)}")
        for vc in vendor_controls:
            print(f"   - {vc.get('Control Ref')}: {vc.get('Control Activity Description', '')[:80]}...")
    
    print("\n" + "=" * 80)
    print("✅ Phase 2 Complete. Proceed to Phase 3 (Validation)")
    print("=" * 80)
    print("Next step: python scope_validator.py")
    print("=" * 80)

if __name__ == "__main__":
    main()