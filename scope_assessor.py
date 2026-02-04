"""
PHASE 0: SCOPE ASSESSOR (Strategic Intelligence)
Analyzes system descriptions to identify subservice organizations and classify
reporting methods (Carve-out vs Inclusive) using LLM-powered semantic reasoning.

This is the FIRST step in the pipeline - it creates the "ground truth" scope strategy
that guides control generation and validation.
"""

import os
import json
import pandas as pd
import sys
from openai import OpenAI
from typing import Dict, List, Optional
from config import OPENAI_API_KEY, SOC2_MODEL

sys.stdout.reconfigure(encoding='utf-8')

# Configuration
client = OpenAI(api_key=OPENAI_API_KEY)

# File paths
SYSTEM_DESCRIPTION_FILE = "system_description.txt"
OUTPUT_FILE = "scope_strategy.json"

# Expert SOC 2 Auditor Persona
AUDITOR_PERSONA = """
You are a Senior Information Security Auditor with over 20 years of experience 
conducting SOC 2 Type 2 examinations under SSAE 21. Your expertise lies in 
interpreting DC Section 200 description criteria. You are highly skeptical and 
require explicit evidence in the text to support your conclusions. You understand 
the nuance between 'user entity controls', 'service organization controls', and 
'subservice organization controls'. Your goal is to map unstructured narratives 
to rigid regulatory frameworks.
"""


def load_system_description(filepath: str) -> str:
    """Load the system description text file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"System description not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def identify_subservice_organizations(description: str) -> Dict:
    """
    Use LLM to identify subservice organizations mentioned in the description.
    Returns a structured analysis of vendors and their roles.
    """
    prompt = f"""
{AUDITOR_PERSONA}

Analyze the following system description and identify ALL subservice organizations 
(vendors, third-party service providers) mentioned. For each, extract:
1. Vendor name (EXACT name as it appears - preserve case and spelling)
2. Service provided (e.g., "compute infrastructure", "identity management")
3. Key phrases indicating reliance (exact quotes from text)

CRITICAL: Preserve exact vendor names. Do NOT normalize or abbreviate.
Example: If text says "Amazon Web Services", use "Amazon Web Services", NOT "AWS".

System Description:
{description}

Return your analysis as valid JSON with this structure:
{{
  "subservice_organizations": [
    {{
      "vendor_name": "AWS",
      "service_provided": "Cloud compute infrastructure",
      "reliance_phrases": ["relies on AWS for compute", "hosted on AWS"]
    }}
  ]
}}
"""
    
    try:
        response = client.chat.completions.create(
            model=SOC2_MODEL,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.15  # Low temperature for determinism
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error identifying subservice organizations: {e}")
        return {"subservice_organizations": []}


def classify_reporting_method(description: str, vendors: List[Dict]) -> Dict:
    """
    Classify the reporting method (Carve-out vs Inclusive) using semantic heuristics.
    """
    vendor_names = [v["vendor_name"] for v in vendors]
    vendor_list_str = ", ".join(vendor_names) if vendor_names else "None identified"
    
    prompt = f"""
{AUDITOR_PERSONA}

Based on the system description, classify the reporting method for subservice 
organizations under SSAE 21 standards.

Identified Vendors: {vendor_list_str}

CLASSIFICATION RULES:
- **CARVE-OUT METHOD**: Subservice controls are EXCLUDED from examination scope.
  Signals: "relies on", "hosted by", "managed by third party", "review SOC 2 report"
  The description does NOT include the vendor's internal controls.

- **INCLUSIVE METHOD**: Subservice controls are INCLUDED in the examination scope.
  Signals: "managed by us", "controls tested by auditor", "assertion provided"
  The description DOES include the vendor's internal control details.

System Description:
{description}

Provide your classification in JSON format with evidence-based reasoning:
{{ 
  "classification": "CARVE_OUT" or "INCLUSIVE" or "UNDETERMINED",
  "confidence": 0.0-1.0,
  "reasoning": "Detailed explanation with quotes from description",
  "evidence": ["Quote 1", "Quote 2"]
}}
"""
    
    try:
        response = client.chat.completions.create(
            model=SOC2_MODEL,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.15
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error classifying reporting method: {e}")
        return {
            "classification": "ERROR",
            "confidence": 0.0,
            "reasoning": str(e),
            "evidence": []
        }


def generate_control_requirements(classification: str, vendors: List[Dict]) -> List[Dict]:
    """
    Generate specific control requirements based on scope classification.
    For CARVE_OUT, this specifies required vendor monitoring controls.
    """
    requirements = []
    
    if classification == "CARVE_OUT" and vendors:
        for vendor in vendors:
            requirements.append({
                "control_type": "CC9.2_VENDOR_MONITORING",
                "vendor_name": vendor["vendor_name"],
                "required_control_description": f"Annual review of {vendor['vendor_name']} SOC 2 Type II report",
                "frequency": "Annual",
                "tsc_criteria": "CC9.2",
                "rationale": f"Carve-out method requires monitoring of {vendor['vendor_name']} subservice organization controls"
            })
    
    return requirements


def generate_oscal_hint(classification: str, vendors: List[Dict]) -> Dict:
    """
    Generate OSCAL leveraged-authorization hints for carve-out scenarios.
    """
    if classification != "CARVE_OUT":
        return {"oscal_leveraged_authorizations": []}
    
    leveraged_auths = []
    for vendor in vendors:
        leveraged_auths.append({
            "vendor": vendor["vendor_name"],
            "service": vendor["service_provided"],
            "oscal_component_type": "leveraged-authorization",
            "recommendation": f"Link to {vendor['vendor_name']} SOC 2 report UUID in OSCAL SSP"
        })
    
    return {"oscal_leveraged_authorizations": leveraged_auths}


def generate_required_language(classification: str) -> str:
    """
    Generate the required disclosure language for the auditor's report.
    """
    if classification == "CARVE_OUT":
        return (
            "The description includes the services of subservice organizations; however, "
            "the controls of these subservice organizations are not included in the scope "
            "of this examination. The user entity should review the SOC 2 reports of the "
            "subservice organizations to assess their control effectiveness."
        )
    elif classification == "INCLUSIVE":
        return (
            "The description includes the services and controls of subservice organizations. "
            "These controls have been tested as part of this examination."
        )
    else:
        return "Manual review required to determine appropriate disclosure language."


def main():
    print("=" * 80)
    print("PHASE 0: SCOPE ASSESSOR (Strategic Intelligence)")
    print("=" * 80)
    
    # Step 1: Load system description
    print("\n[1/4] Loading system description...")
    try:
        description = load_system_description(SYSTEM_DESCRIPTION_FILE)
        print(f"✓ Loaded {len(description)} characters")
    except FileNotFoundError as e:
        print(f"✗ {e}")
        print("\nCreate a 'system_description.txt' file with the organization's system description.")
        return
    
    # Step 2: Identify subservice organizations
    print("\n[2/4] Identifying subservice organizations...")
    vendor_analysis = identify_subservice_organizations(description)
    vendors = vendor_analysis.get("subservice_organizations", [])
    print(f"✓ Identified {len(vendors)} subservice organization(s):")
    for v in vendors:
        print(f"   - {v['vendor_name']}: {v['service_provided']}")
    
    # Step 3: Classify reporting method
    print("\n[3/4] Classifying reporting method...")
    classification_result = classify_reporting_method(description, vendors)
    classification = classification_result.get("classification", "UNDETERMINED")
    confidence = classification_result.get("confidence", 0.0)
    print(f"✓ Classification: {classification} (confidence: {confidence:.2%})")
    print(f"   Reasoning: {classification_result.get('reasoning', 'N/A')[:150]}...")
    
    # Step 4: Generate control requirements
    print("\n[4/4] Generating control requirements...")
    control_requirements = generate_control_requirements(classification, vendors)
    print(f"✓ Generated {len(control_requirements)} required control(s)")
    
    # Build scope strategy
    scope_strategy = {
        "phase": "PHASE_0_SCOPE_ASSESSMENT",
        "timestamp": pd.Timestamp.now().isoformat(),
        "system_description_file": SYSTEM_DESCRIPTION_FILE,
        "subservice_organizations": vendors,
        "reporting_method": {
            "classification": classification,
            "confidence": confidence,
            "reasoning": classification_result.get("reasoning", ""),
            "evidence": classification_result.get("evidence", [])
        },
        "required_controls": control_requirements,
        "oscal_integration": generate_oscal_hint(classification, vendors),
        "required_disclosure_language": generate_required_language(classification)
    }
    
    # Save scope strategy
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(scope_strategy, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Scope strategy saved to: {OUTPUT_FILE}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SCOPE STRATEGY SUMMARY")
    print("=" * 80)
    print(f"Subservice Organizations: {len(vendors)}")
    print(f"Reporting Method: {classification} ({confidence:.1%} confidence)")
    print(f"Required Controls: {len(control_requirements)}")
    print("=" * 80)
    print("\n✅ Phase 0 Complete. Proceed to Phase 1 (Control Generation)")
    print("=" * 80)


if __name__ == "__main__":
    main()
