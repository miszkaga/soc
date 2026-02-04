"""
PHASE 2: SCOPE VALIDATOR (The Gatekeeper)
Validates RAW controls against scope strategy BEFORE sanitization.

This is the CRITICAL quality gate that prevents "Identity Loss" by validating
controls while vendor names are still intact.

CRITICAL: This runs AFTER control generation but BEFORE sanitization.
"""

import os
import json
import pandas as pd
from typing import Dict, List
from datetime import datetime

# File paths
SCOPE_STRATEGY_FILE = "scope_strategy.json"
CONTROLS_FILE = "controls.xlsx"
OUTPUT_FILE = "scope_validation_report.json"

def load_scope_strategy(filepath: str) -> Dict:
    """Load the scope strategy from Phase 0."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Scope strategy not found: {filepath}. Run scope_assessor.py first.")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_controls(filepath: str) -> pd.DataFrame:
    """Load the RAW controls file (before sanitization)."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Controls file not found: {filepath}. Run rcm_generator.py first.")
    
    return pd.read_excel(filepath)

def validate_vendor_monitoring_controls(df: pd.DataFrame, scope_strategy: Dict) -> Dict:
    """
    CRITICAL VALIDATION: Check if required vendor monitoring controls exist.
    This MUST run on RAW controls before vendor names are sanitized to [VENDOR].
    """
    required_controls = scope_strategy.get("required_controls", [])
    vendors = scope_strategy.get("subservice_organizations", [])
    classification = scope_strategy.get("reporting_method", {}).get("classification", "")
    
    # If not carve-out, no vendor monitoring controls required
    if classification != "CARVE_OUT" or not vendors:
        return {
            "status": "PASS",
            "message": "No vendor monitoring controls required (not carve-out method)",
            "missing_controls": [],
            "found_controls": []
        }
    
    # Search for controls that mention each vendor
    vendor_names = [v["vendor_name"] for v in vendors]
    found_controls = []
    missing_vendors = []
    
    # Detect control description column
    control_desc_col = None
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ['description', 'activity', 'control']):
            control_desc_col = col
            break
    
    if not control_desc_col:
        return {
            "status": "ERROR",
            "message": "Could not detect control description column",
            "missing_controls": [],
            "found_controls": []
        }
    
    # Check each vendor
    for vendor in vendors:
        vendor_name = vendor["vendor_name"]
        monitoring_keywords = ["review", "SOC 2", "report", "monitoring", "assessment"]
        
        # Search for controls mentioning this vendor AND monitoring activities
        vendor_controls = []
        for idx, row in df.iterrows():
            control_text = str(row.get(control_desc_col, "")).lower()
            control_ref = row.get("Control Ref", f"Row-{idx}")
            
            # Check if control mentions vendor name
            if vendor_name.lower() in control_text:
                # Check if it's a monitoring control
                has_monitoring = any(keyword in control_text for keyword in monitoring_keywords)
                
                if has_monitoring:
                    vendor_controls.append({
                        "control_ref": control_ref,
                        "vendor": vendor_name,
                        "control_text": str(row.get(control_desc_col, ""))[:200] + "..."
                    })
        
        if vendor_controls:
            found_controls.extend(vendor_controls)
        else:
            missing_vendors.append(vendor_name)
    
    # Determine validation status
    if missing_vendors:
        return {
            "status": "FAIL",
            "message": f"Missing required CC9.2 vendor monitoring controls for: {', '.join(missing_vendors)}",
            "missing_controls": [
                {
                    "vendor": v,
                    "required_control": f"Annual review of {v} SOC 2 Type II report",
                    "tsc_criteria": "CC9.2"
                } for v in missing_vendors
            ],
            "found_controls": found_controls
        }
    else:
        return {
            "status": "PASS",
            "message": f"All required vendor monitoring controls found ({len(found_controls)} controls)",
            "missing_controls": [],
            "found_controls": found_controls
        }

def validate_control_completeness(df: pd.DataFrame) -> Dict:
    """Validate that controls have required fields and proper structure."""
    issues = []
    
    # Check for required columns
    required_cols = ["Control Ref"]
    for col in required_cols:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")
    
    # Check for empty controls
    control_desc_col = None
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ['description', 'activity', 'control']):
            control_desc_col = col
            break
    
    if control_desc_col:
        empty_count = df[control_desc_col].isna().sum()
        if empty_count > 0:
            issues.append(f"{empty_count} controls have empty descriptions")
    
    if issues:
        return {
            "status": "WARNING",
            "message": "Control structure issues detected",
            "issues": issues
        }
    else:
        return {
            "status": "PASS",
            "message": "Control structure validation passed",
            "issues": []
        }

def generate_remediation_guidance(validation_result: Dict, scope_strategy: Dict) -> List[Dict]:
    """Generate actionable remediation steps if validation fails."""
    if validation_result["status"] != "FAIL":
        return []
    
    recommendations = []
    
    for missing in validation_result.get("missing_controls", []):
        vendor = missing["vendor"]
        recommendations.append({
            "priority": "HIGH",
            "action": "ADD_CONTROL",
            "vendor": vendor,
            "suggested_control": {
                "Control Ref": "CC9.2-VENDOR",
                "Control Activity Description": f"On an annual basis, the Security Team reviews the SOC 2 Type II report for {vendor} to ensure the subservice organization maintains adequate controls. Any exceptions or qualifications identified in the report are documented and escalated to management for remediation tracking.",
                "Frequency": "Annual",
                "Owner": "Security Team",
                "TSC Criteria": "CC9.2"
            },
            "rationale": f"SSAE 21 requires carve-out method to include monitoring controls for subservice organizations. {vendor} is a critical subservice organization that must be monitored."
        })
    
    return recommendations

def main():
    print("=" * 80)
    print("PHASE 2: SCOPE VALIDATOR (The Gatekeeper)")
    print("=" * 80)
    print("⚠️  CRITICAL: This validates RAW controls BEFORE sanitization")
    print("=" * 80)
    
    # Step 1: Load scope strategy
    print("\n[1/4] Loading scope strategy from Phase 0...")
    try:
        scope_strategy = load_scope_strategy(SCOPE_STRATEGY_FILE)
        classification = scope_strategy.get("reporting_method", {}).get("classification", "UNKNOWN")
        vendors = scope_strategy.get("subservice_organizations", [])
        print(f"✓ Loaded scope strategy: {classification} method with {len(vendors)} vendor(s)")
    except FileNotFoundError as e:
        print(f"✗ {e}")
        return {"status": "ERROR", "message": str(e)}
    
    # Step 2: Load RAW controls
    print("\n[2/4] Loading RAW controls (before sanitization)...")
    try:
        df = load_controls(CONTROLS_FILE)
        print(f"✓ Loaded {len(df)} controls from {CONTROLS_FILE}")
    except FileNotFoundError as e:
        print(f"✗ {e}")
        return {"status": "ERROR", "message": str(e)}
    
    # Step 3: Validate vendor monitoring controls
    print("\n[3/4] Validating vendor monitoring controls...")
    vendor_validation = validate_vendor_monitoring_controls(df, scope_strategy)
    print(f"{'✓' if vendor_validation['status'] == 'PASS' else '✗'} {vendor_validation['message']}")
    
    if vendor_validation.get("found_controls"):
        print(f"   Found {len(vendor_validation['found_controls'])} vendor monitoring control(s):")
        for ctrl in vendor_validation["found_controls"]:
            print(f"   - {ctrl['control_ref']}: {ctrl['vendor']}")
    
    if vendor_validation.get("missing_controls"):
        print(f"   ⚠️  Missing {len(vendor_validation['missing_controls'])} required control(s):")
        for missing in vendor_validation["missing_controls"]:
            print(f"   - {missing['vendor']}: {missing['required_control']}")
    
    # Step 4: Validate control structure
    print("\n[4/4] Validating control structure...")
    structure_validation = validate_control_completeness(df)
    print(f"{'✓' if structure_validation['status'] == 'PASS' else '⚠️'} {structure_validation['message']}")
    
    # Generate remediation guidance
    remediation = generate_remediation_guidance(vendor_validation, scope_strategy)
    
    # Determine overall validation result
    overall_status = "PASS"
    if vendor_validation["status"] == "FAIL":
        overall_status = "FAIL"
    elif structure_validation["status"] == "WARNING":
        overall_status = "WARNING"
    
    # Build validation report
    validation_report = {
        "phase": "PHASE_2_SCOPE_VALIDATION",
        "timestamp": datetime.now().isoformat(),
        "overall_status": overall_status,
        "scope_strategy_file": SCOPE_STRATEGY_FILE,
        "controls_file": CONTROLS_FILE,
        "validations": {
            "vendor_monitoring": vendor_validation,
            "control_structure": structure_validation
        },
        "remediation_guidance": remediation,
        "pipeline_decision": {
            "proceed_to_sanitization": overall_status == "PASS",
            "reason": "All validations passed" if overall_status == "PASS" else "Validation failures detected - must remediate before proceeding"
        }
    }
    
    # Save validation report
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(validation_report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Validation report saved to: {OUTPUT_FILE}")
    
    # Summary and decision
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Overall Status: {overall_status}")
    print(f"Vendor Monitoring: {vendor_validation['status']}")
    print(f"Control Structure: {structure_validation['status']}")
    
    if overall_status == "PASS":
        print("\n✅ VALIDATION PASSED - Pipeline may proceed to sanitization")
        print("=" * 80)
        print("Next step: python sanitazer/automated_sanitizer.py")
        print("=" * 80)
        return validation_report
    else:
        print("\n❌ VALIDATION FAILED - Pipeline HALTED")
        print("=" * 80)
        print(f"Issues found: {len(remediation)}")
        print("\nRemediation required:")
        for idx, rec in enumerate(remediation, 1):
            print(f"\n{idx}. Add CC9.2 control for {rec['vendor']}")
            print(f"   Suggested: {rec['suggested_control']['Control Activity Description'][:100]}...")
        print("\n=" * 80)
        print("⚠️  DO NOT PROCEED TO SANITIZATION UNTIL DEFICIENCIES ARE RESOLVED")
        print("=" * 80)
        
        # Exit with error code if validation failed
        import sys
        sys.exit(1)


if __name__ == "__main__":
    result = main()