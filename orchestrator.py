#!/usr/bin/env python3
"""
MASTER ORCHESTRATOR: SOC 2 Audit Automation Pipeline
Executes the complete pipeline with quality gates and validation checkpoints.

EXECUTION ORDER (Shift-Left Architecture):
  Phase 0: Scope Assessor     → Analyzes system description, identifies vendors
  Phase 1: Control Generator   → Generates scope-aware controls (RAW)
  Phase 2: Scope Validator     → ⚠️ QUALITY GATE: Validates RAW controls
  Phase 3: Sanitization        → Sanitizer → Mapper → Auditor (only if Phase 2 passes)

CRITICAL: Phase 2 validation runs BEFORE sanitization to prevent "Identity Loss"
"""

import subprocess
import sys
import json
import os
from datetime import datetime
from typing import Dict, Tuple

# Color codes for terminal output
class Colors:
    HEADER = '\x1b[95m'
    OKBLUE = '\x1b[94m'
    OKCYAN = '\x1b[96m'
    OKGREEN = '\x1b[92m'
    WARNING = '\x1b[93m'
    FAIL = '\x1b[91m'
    ENDC = '\x1b[0m'
    BOLD = '\x1b[1m'
    UNDERLINE = '\x1b[4m'

def print_phase_header(phase: str, description: str):
    """Print a formatted phase header."""
    print(
" + " "=" * 80)
    print(f"{Colors.HEADER}{Colors.BOLD}{phase}: {description}{Colors.ENDC}")
    print("=" * 80 + "\n")

def print_success(message: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")

def print_error(message: str):
    """Print error message."""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")

def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")

def run_python_script(script_path: str, phase_name: str) -> Tuple[bool, str]:
    """
    Execute a Python script and return success status.
    
    Returns:
        Tuple[bool, str]: (success, output)
    """
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Print the output
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        # Check return code
        success = result.returncode == 0
        return success, result.stdout + result.stderr
    
    except Exception as e:
        print_error(f"Failed to execute {script_path}: {e}")
        return False, str(e)

def load_validation_report() -> Dict:
    """Load the validation report from Phase 2."""
    try:
        with open("none_ex_files/scope_validation_report.json", 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def phase_0_scope_assessment() -> bool:
    """Phase 0: Strategic Intelligence - Scope Assessment"""
    print_phase_header("PHASE 0", "Strategic Intelligence (Scope Assessment)")
    
    if not os.path.exists("none_ex_files/system_description.txt"):
        print_error("system_description.txt not found!")
        print("Please create this file with your organization's system description.")
        return False
    
    success, output = run_python_script("scope_assessor.py", "Phase 0")
    
    if success:
        print_success("Phase 0 Complete: Scope strategy generated")
        
        # Load and display summary
        try:
            with open("none_ex_files/scope_strategy.json", 'r') as f:
                strategy = json.load(f)
                classification = strategy.get("reporting_method", {}).get("classification", "UNKNOWN")
                vendors = strategy.get("subservice_organizations", [])
                print(f"\n📋 Scope Summary:")
                print(f"   Classification: {classification}")
                print(f"   Vendors: {len(vendors)}")
                for v in vendors:
                    print(f"      - {v['vendor_name']}")
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print_warning(f"Could not read scope strategy summary: {e}")
        
        return True
    else:
        print_error("Phase 0 Failed")
        return False

def phase_1_control_generation() -> bool:
    """Phase 1: Intelligent Control Generation (Scope-Aware)"""
    print_phase_header("PHASE 1", "Intelligent Control Generation (Scope-Aware)")
    
    success, output = run_python_script("rcm_generator.py", "Phase 1")
    
    if success:
        print_success("Phase 1 Complete: Controls generated")
        
        # Check if controls file exists
        if os.path.exists("none_ex_files/controls.xlsx"):
            import pandas as pd
            df = pd.read_excel("none_ex_files/controls.xlsx")
            print(f"\n📋 Generated {len(df)} controls")
            
            # Count vendor controls
            vendor_controls = df[df['Control Ref'].str.contains('CC9.2', na=False)]
            if not vendor_controls.empty:
                print(f"   Including {len(vendor_controls)} vendor monitoring controls")
        
        return True
    else:
        print_error("Phase 1 Failed")
        return False

def phase_2_validation() -> bool:
    """Phase 2: The Gatekeeper - Validation of RAW Controls"""
    print_phase_header("PHASE 2", "The Gatekeeper (Validation of RAW Controls)")
    print_warning("CRITICAL: Validating controls BEFORE sanitization to prevent Identity Loss")
    
    success, output = run_python_script("scope_validator.py", "Phase 2")
    
    # Load validation report
    validation_report = load_validation_report()
    overall_status = validation_report.get("overall_status", "UNKNOWN")
    
    if success and overall_status == "PASS":
        print_success("Phase 2 Complete: All validations PASSED")
        print(f"{Colors.OKGREEN}{Colors.BOLD}✅ QUALITY GATE PASSED - Proceeding to sanitization{Colors.ENDC}")
        return True
    else:
        print_error("Phase 2 Failed: Validation checks failed")
        print(f"{Colors.FAIL}{Colors.BOLD}🚨 QUALITY GATE FAILED - Pipeline HALTED{Colors.ENDC}")
        
        # Display deficiencies
        if validation_report:
            remediation = validation_report.get("remediation_guidance", [])
            if remediation:
                print(f"\n{Colors.WARNING}Deficiencies requiring remediation:{Colors.ENDC}")
                for idx, rec in enumerate(remediation, 1):
                    print(f"\n{idx}. Missing control for vendor: {rec.get('vendor')}")
                    suggested = rec.get('suggested_control', {})
                    print(f"   Suggested: {suggested.get('Control Activity Description', '')[:100]}...")
        
        print(f"\n{Colors.FAIL}⛔ DO NOT PROCEED until deficiencies are resolved{Colors.ENDC}")
        print("Options:")
        print("  1. Manually add missing controls to none_ex_files/controls.xlsx")
        print("  2. Update none_ex_files/system_description.txt and re-run from Phase 0")
        print("  3. Re-run Phase 2 after fixes: python scope_validator.py")
        
        return False

def phase_3_sanitization_pipeline() -> bool:
    """Phase 3: Production Factory - Sanitization Pipeline"""
    print_phase_header("PHASE 3", "Production Factory (Sanitization Pipeline)")
    
    # 3.1: Sanitizer
    print(f"\n{Colors.OKCYAN}[3.1] Running Sanitizer...{Colors.ENDC}")
    success, _ = run_python_script("automated_sanitizer.py", "Sanitizer")
    if not success:
        print_error("Sanitizer failed")
        return False
    print_success("Sanitizer complete")
    
    # 3.2: Mapper (RAG)
    print(f"\n{Colors.OKCYAN}[3.2] Running Mapper (RAG)...{Colors.ENDC}")
    success, _ = run_python_script("modul_2_mapper_rag.py", "Mapper")
    if not success:
        print_error("Mapper failed")
        return False
    print_success("Mapper complete")
    
    # 3.3: Auditor
    print(f"\n{Colors.OKCYAN}[3.3] Running Auditor (Procedure Generator)...{Colors.ENDC}")
    success, _ = run_python_script("auditor.py", "Auditor")
    if not success:
        print_error("Auditor failed")
        return False
    print_success("Auditor complete")
    
    print_success("Phase 3 Complete: Sanitization pipeline finished")
    return True

def generate_pipeline_report(start_time: datetime, phases_completed: list):
    """Generate final pipeline execution report."""
    end_time = datetime.now()
    duration = end_time - start_time
    
    print("\n" + "=" * 80)
    print(f"{Colors.HEADER}{Colors.BOLD}PIPELINE EXECUTION REPORT{Colors.ENDC}")
    print("=" * 80)
    print(f"\nStart Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration.total_seconds():.2f} seconds")
    
    print(f"\nPhases Completed:")
    for phase in phases_completed:
        print(f"  ✅ {phase}")
    
    print("\nGenerated Files:")
    files = [
        ("none_ex_files/scope_strategy.json", "Scope strategy from Phase 0"),
        ("none_ex_files/controls.xlsx", "RAW controls from Phase 1"),
        ("none_ex_files/scope_validation_report.json", "Validation report from Phase 2"),
        ("none_ex_files/sanitized_controls.xlsx", "Sanitized controls"),
        ("none_ex_files/mapped_controls_rag.xlsx", "Mapped controls with TSC"),
        ("none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx", "Final audit procedures")
    ]
    
    for filename, description in files:
        if os.path.exists(filename):
            print(f"  ✅ {filename} - {description}")
        else:
            print(f"  ⚠️  {filename} - Not generated")
    
    print("\n" + "=" * 80)

def main():
    """Main orchestrator function."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔═══════════════════════════════════════════════════════════════════════════════╗")
    print("║                   SOC 2 AUDIT AUTOMATION PIPELINE                             ║")
    print("║                   Master Orchestrator (Shift-Left Architecture)               ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    start_time = datetime.now()
    phases_completed = []
    
    try:
        # Phase 0: Scope Assessment
        if not phase_0_scope_assessment():
            print_error("Pipeline halted at Phase 0")
            sys.exit(1)
        phases_completed.append("Phase 0: Scope Assessment")
        
        # Phase 1: Control Generation
        if not phase_1_control_generation():
            print_error("Pipeline halted at Phase 1")
            sys.exit(1)
        phases_completed.append("Phase 1: Control Generation")
        
        # Phase 2: Validation (THE GATEKEEPER)
        if not phase_2_validation():
            print_error("Pipeline halted at Phase 2 (QUALITY GATE FAILED)")
            print("\n" + "=" * 80)
            print(f"{Colors.FAIL}{Colors.BOLD}⛔ PIPELINE STOPPED DUE TO VALIDATION FAILURES{Colors.ENDC}")
            print("=" * 80)
            generate_pipeline_report(start_time, phases_completed)
            sys.exit(1)
        phases_completed.append("Phase 2: Validation (Quality Gate PASSED)")
        
        # Phase 3: Sanitization Pipeline (only if validation passed)
        if not phase_3_sanitization_pipeline():
            print_error("Pipeline halted at Phase 3")
            sys.exit(1)
        phases_completed.append("Phase 3: Sanitization Pipeline")
        
        # Success!
        print("\n" + "=" * 80)
        print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 PIPELINE COMPLETED SUCCESSFULLY!{Colors.ENDC}")
        print("=" * 80)
        
        generate_pipeline_report(start_time, phases_completed)
        
        print(f"\n{Colors.OKGREEN}✅ All phases completed. Final audit procedures ready.{Colors.ENDC}")
        print(f"\nFinal Output: {Colors.BOLD}none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx{Colors.ENDC}")
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Pipeline interrupted by user{Colors.ENDC}")
        generate_pipeline_report(start_time, phases_completed)
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        generate_pipeline_report(start_time, phases_completed)
        sys.exit(1)

if __name__ == "__main__":
    main()