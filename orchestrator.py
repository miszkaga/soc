#!/usr/bin/env python3
"""
MASTER ORCHESTRATOR: SOC 2 Audit Automation Pipeline
Executes the complete pipeline with quality gates and validation checkpoints.

EXECUTION ORDER (Privacy-First Architecture):
  Phase 0:   System Description Sanitizer  → Anonymises the system description
                                             BEFORE any LLM call (no API involved)
  Phase 0.5: Semantic Token Enrichment     → Local Ollama enriches tokens with
                                             short context labels (graceful fallback)
  Phase 1:   Scope Assessor     → Analyses enriched-sanitized description
  Phase 2:   Control Generator  → Generates scope-aware controls (RAW, sanitized)
  Phase 3:   Scope Validator    → ⚠️ QUALITY GATE: Validates RAW controls
  Phase 4:   Sanitization       → Mapper → Auditor (only if Phase 3 passes)
  Phase 5:   Report Re-hydrator → Restores original names in final Excel output

CRITICAL: Sensitive data never reaches the LLM API – it is replaced with
          anonymous tokens by Phase 0 before Phase 1 begins.
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
        "\n" + "=" * 80)
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

def phase_0_sanitize_system_description() -> bool:
    """Phase 0: Algorithmic sanitization of the raw system description (no API)."""
    print_phase_header("PHASE 0", "System Description Sanitizer (Privacy Guard – No API Calls)")

    if not os.path.exists("none_ex_files/system_description.txt"):
        print_error("system_description.txt not found!")
        print("Please create none_ex_files/system_description.txt and re-run.")
        return False

    success, output = run_python_script("system_description_sanitizer.py", "Phase 0")

    if success:
        print_success("Phase 0 Complete: System description sanitized")
        if os.path.exists("none_ex_files/system_description_sensitive_map.json"):
            try:
                with open("none_ex_files/system_description_sensitive_map.json") as f:
                    sensitive_map = json.load(f)
                print(f"\n🔐 Replaced {len(sensitive_map)} unique sensitive entities with anonymous tokens")
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return True
    else:
        print_error("Phase 0 Failed: Sanitizer encountered an error")
        return False


def phase_0_5_enrich_tokens() -> bool:
    """Phase 0.5: Semantic Token Enrichment via local Ollama (graceful fallback)."""
    print_phase_header(
        "PHASE 0.5",
        "Semantic Token Enrichment (Local Ollama – No External API, Graceful Fallback)",
    )

    if not os.path.exists("none_ex_files/system_description_sensitive_map.json"):
        print_warning("Sensitive map not found – skipping token enrichment.")
        return True  # Non-fatal: rest of pipeline can proceed without enrichment

    success, _ = run_python_script("phase_0_5_map_enricher.py", "Phase 0.5")

    if success:
        print_success("Phase 0.5 Complete: Token enrichment finished")
        if os.path.exists("none_ex_files/enriched_sensitive_map.json"):
            try:
                with open("none_ex_files/enriched_sensitive_map.json") as f:
                    enriched_map = json.load(f)
                enriched_count = sum(1 for t in enriched_map.values() if ":" in t)
                print(
                    f"\n🏷️  {enriched_count}/{len(enriched_map)} tokens enriched with "
                    f"Ollama context labels"
                )
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return True
    else:
        # Phase 0.5 failures are non-fatal – pipeline can continue with plain tokens
        print_warning(
            "Phase 0.5 encountered an error. Pipeline will continue with plain tokens."
        )
        return True


def phase_1_scope_assessment() -> bool:
    """Phase 1: Strategic Intelligence - Scope Assessment (uses sanitized description)"""
    print_phase_header("PHASE 1", "Strategic Intelligence (Scope Assessment)")

    if not os.path.exists("none_ex_files/sanitized_system_description.txt"):
        print_warning("Sanitized description not found – scope assessor will use raw file.")
        if not os.path.exists("none_ex_files/system_description.txt"):
            print_error("system_description.txt not found!")
            return False

    success, output = run_python_script("scope_assessor.py", "Phase 1")

    if success:
        print_success("Phase 1 Complete: Scope strategy generated")

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
        print_error("Phase 1 Failed")
        return False


def phase_2_control_generation() -> bool:
    """Phase 2: Intelligent Control Generation (Scope-Aware, uses sanitized input)"""
    print_phase_header("PHASE 2", "Intelligent Control Generation (Scope-Aware)")

    success, output = run_python_script("rcm_generator.py", "Phase 2")

    if success:
        print_success("Phase 2 Complete: Controls generated")

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
        print_error("Phase 2 Failed")
        return False


def phase_3_validation() -> bool:
    """Phase 3: The Gatekeeper - Validation of RAW Controls"""
    print_phase_header("PHASE 3", "The Gatekeeper (Validation of RAW Controls)")

    success, output = run_python_script("scope_validator.py", "Phase 3")

    # Load validation report
    validation_report = load_validation_report()
    overall_status = validation_report.get("overall_status", "UNKNOWN")

    if success and overall_status == "PASS":
        print_success("Phase 3 Complete: All validations PASSED")
        print(f"{Colors.OKGREEN}{Colors.BOLD}✅ QUALITY GATE PASSED - Proceeding to audit procedures{Colors.ENDC}")
        return True
    else:
        print_error("Phase 3 Failed: Validation checks failed")
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
        print("  3. Re-run Phase 3 after fixes: python scope_validator.py")

        return False


def phase_4_audit_pipeline() -> bool:
    """Phase 4: Production Factory – Controls Sanitizer (safety net) + Mapper + Auditor"""
    print_phase_header("PHASE 4", "Production Factory (Controls Sanitizer + Mapper + Auditor)")

    # 4.1: Controls Sanitizer – algorithmic safety net, no API
    print(f"\n{Colors.OKCYAN}[4.1] Running Controls Sanitizer (algorithmic safety net)...{Colors.ENDC}")
    success, _ = run_python_script("automated_sanitizer.py", "Controls Sanitizer")
    if not success:
        print_error("Controls Sanitizer failed")
        return False
    print_success("Controls Sanitizer complete")

    # 4.2: Mapper (RAG)
    print(f"\n{Colors.OKCYAN}[4.2] Running Mapper (RAG)...{Colors.ENDC}")
    success, _ = run_python_script("modul_2_mapper_rag.py", "Mapper")
    if not success:
        print_error("Mapper failed")
        return False
    print_success("Mapper complete")

    # 4.3: Auditor
    print(f"\n{Colors.OKCYAN}[4.3] Running Auditor (Procedure Generator)...{Colors.ENDC}")
    success, _ = run_python_script("auditor.py", "Auditor")
    if not success:
        print_error("Auditor failed")
        return False
    print_success("Auditor complete")

    print_success("Phase 4 Complete: Audit pipeline finished")
    return True


def phase_5_rehydrate_report() -> bool:
    """Phase 5: Re-hydrate the final Excel report with original sensitive names."""
    print_phase_header(
        "PHASE 5",
        "Report Re-hydrator (Restore Original Names in Final Excel Output)",
    )

    if not os.path.exists("none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx"):
        print_warning("Final audit workbook not found – skipping re-hydration.")
        return True  # Non-fatal

    success, _ = run_python_script("phase_5_rehydrator.py", "Phase 5")

    if success:
        print_success("Phase 5 Complete: Auditor-ready report generated")
        if os.path.exists("none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx"):
            print(
                f"\n📋 Final Output (with real names restored): "
                f"none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx"
            )
        return True
    else:
        print_warning(
            "Phase 5 encountered an error. "
            "The anonymised workbook is still available at "
            "none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx"
        )
        return True  # Non-fatal – pipeline succeeded, re-hydration is a post-processing step

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
        ("none_ex_files/system_description_sensitive_map.json", "Sensitive entity map (Phase 0)"),
        ("none_ex_files/sanitized_system_description.txt", "Sanitized system description (Phase 0)"),
        ("none_ex_files/enriched_sensitive_map.json", "Enriched token map (Phase 0.5)"),
        ("none_ex_files/scope_strategy.json", "Scope strategy (Phase 1)"),
        ("none_ex_files/controls.xlsx", "RAW controls (Phase 2)"),
        ("none_ex_files/scope_validation_report.json", "Validation report (Phase 3)"),
        ("none_ex_files/mapped_controls_rag.xlsx", "Mapped controls with TSC (Phase 4)"),
        ("none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx", "Final audit procedures (Phase 4)"),
        ("none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx", "Auditor-ready report with real names (Phase 5)"),
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
        # Phase 0: Sanitize system description (no API calls)
        if not phase_0_sanitize_system_description():
            print_error("Pipeline halted at Phase 0")
            sys.exit(1)
        phases_completed.append("Phase 0: System Description Sanitizer")

        # Phase 0.5: Enrich tokens via local Ollama (graceful fallback if unavailable)
        phase_0_5_enrich_tokens()
        phases_completed.append("Phase 0.5: Semantic Token Enrichment (Ollama)")

        # Phase 1: Scope Assessment (reads sanitized/enriched description)
        if not phase_1_scope_assessment():
            print_error("Pipeline halted at Phase 1")
            sys.exit(1)
        phases_completed.append("Phase 1: Scope Assessment")

        # Phase 2: Control Generation (reads sanitized description)
        if not phase_2_control_generation():
            print_error("Pipeline halted at Phase 2")
            sys.exit(1)
        phases_completed.append("Phase 2: Control Generation")

        # Phase 3: Validation (THE GATEKEEPER)
        if not phase_3_validation():
            print_error("Pipeline halted at Phase 3 (QUALITY GATE FAILED)")
            print("\n" + "=" * 80)
            print(f"{Colors.FAIL}{Colors.BOLD}⛔ PIPELINE STOPPED DUE TO VALIDATION FAILURES{Colors.ENDC}")
            print("=" * 80)
            generate_pipeline_report(start_time, phases_completed)
            sys.exit(1)
        phases_completed.append("Phase 3: Validation (Quality Gate PASSED)")

        # Phase 4: Audit Pipeline (only if validation passed)
        if not phase_4_audit_pipeline():
            print_error("Pipeline halted at Phase 4")
            sys.exit(1)
        phases_completed.append("Phase 4: Audit Pipeline (Mapper + Auditor)")

        # Phase 5: Re-hydrate final report with original names (non-fatal)
        phase_5_rehydrate_report()
        phases_completed.append("Phase 5: Report Re-hydrator")

        # Success!
        print("\n" + "=" * 80)
        print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 PIPELINE COMPLETED SUCCESSFULLY!{Colors.ENDC}")
        print("=" * 80)
        
        generate_pipeline_report(start_time, phases_completed)
        
        print(f"\n{Colors.OKGREEN}✅ All phases completed. Final audit procedures ready.{Colors.ENDC}")
        print(f"\nFinal Output (anonymised): {Colors.BOLD}none_ex_files/FINAL_SOC2_AUDIT_ENGLISH.xlsx{Colors.ENDC}")
        print(f"Final Output (real names): {Colors.BOLD}none_ex_files/READY_FOR_AUDITOR_ENGLISH.xlsx{Colors.ENDC}")
        
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