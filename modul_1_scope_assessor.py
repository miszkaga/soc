"""
MODULE 1: SOC 2 Scope Assessment Engine
Analyzes system descriptions to determine subservice organization treatment
and generates preliminary scope boundaries using RAG + LLM reasoning.
"""

import os
import json
import pandas as pd
from typing import Dict, List, Tuple
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import OPENAI_API_KEY, SOC2_MODEL

# Configuration
client = OpenAI(api_key=OPENAI_API_KEY)
INDEX_PATH = "soc2_vector_index"
SYSTEM_DESC_FILE = "system_description.txt"
OUTPUT_FILE = "scope_assessment_results.json"

# Expert SOC 2 Auditor Persona
AUDITOR_PERSONA = """
You are a Senior Information Security Auditor with 20+ years conducting SOC 2 Type 2 
examinations under SSAE 21. You specialize in DC Section 200 description criteria.

CRITICAL INSTRUCTIONS:
1. You are HIGHLY SKEPTICAL and require EXPLICIT textual evidence
2. Distinguish between:
   - User Entity Controls (what clients must do)
   - Service Organization Controls (what the entity does)
   - Subservice Organization Controls (what vendors do)
3. For subservice orgs, determine: CARVE-OUT vs INCLUSIVE method
4. Apply Chain-of-Thought reasoning
5. Output ONLY valid JSON

CARVE-OUT indicators:
- "relies on", "hosted by", "uses", "leverages"
- Vendor controls NOT described in detail
- Company reviews vendor SOC 2 reports

INCLUSIVE indicators:
- "manages", "oversees", "tests", "audits"
- Vendor controls described in system description
- Company has management assertion from vendor
"""


class ScopeAssessor:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.embeddings = OpenAIEmbeddings(api_key=api_key)
        self.vector_store = None
        
    def load_knowledge_base(self) -> bool:
        """Load SSAE 21 and TSC standards from vector index"""
        if not os.path.exists(INDEX_PATH):
            print(f"❌ Vector index not found at {INDEX_PATH}")
            print("   Run 'prepare_vectors.py' first with SSAE 21 and TSC PDFs")
            return False
        
        self.vector_store = FAISS.load_local(
            INDEX_PATH, 
            self.embeddings, 
            allow_dangerous_deserialization=True
        )
        return True
    
    def retrieve_standards_context(self, query: str, k: int = 5) -> str:
        """Retrieve relevant passages from standards"""
        if not self.vector_store:
            return ""
        
        docs = self.vector_store.similarity_search(query, k=k)
        return "\n\n---STANDARD EXCERPT---\n\n".join([d.page_content for d in docs])
    
    def analyze_system_description(self, system_text: str) -> Dict:
        """
        Main scope assessment logic using LLM + RAG
        """
        # Step 1: Retrieve relevant standards context
        context_query = (
            "subservice organization carve-out method inclusive method "
            "complementary user entity controls DC section 200"
        )
        standards_context = self.retrieve_standards_context(context_query)
        
        # Step 2: Construct LLM prompt
        prompt = f"""
{AUDITOR_PERSONA}

TASK:
Analyze the following System Description and determine:
1. List ALL subservice organizations mentioned
2. For EACH subservice, determine: CARVE-OUT or INCLUSIVE method
3. Identify if any User Entity Controls are required
4. Provide evidence-based rationale

STANDARDS CONTEXT:
{standards_context}

SYSTEM DESCRIPTION:
{system_text}

OUTPUT FORMAT (strict JSON):
{{
  "subservice_organizations": [
    {{
      "name": "AWS",
      "method": "CARVE-OUT",
      "evidence": "Text uses 'relies on AWS for compute' with no description of AWS internal controls",
      "services_provided": ["Infrastructure hosting", "Database services"],
      "monitoring_control_required": true
    }}
  ],
  "user_entity_controls": [
    {{
      "description": "Review AWS SOC 2 Type 2 report annually",
      "rationale": "Required complementary control for carved-out infrastructure"
    }}
  ],
  "scope_boundary": "In-scope: Application logic, access management. Out-of-scope: Physical datacenter security (AWS)",
  "confidence_score": 0.95,
  "auditor_notes": "Clear carve-out pattern - no vendor control descriptions present"
}}
"""
        
        # Step 3: Call LLM
        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": AUDITOR_PERSONA},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low for consistency
                max_tokens=2000
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return {"error": str(e)}
    
    def detect_subservice_method_heuristic(self, text: str, vendor: str) -> str:
        """
        Fallback heuristic-based detection (no LLM)
        """
        text_lower = text.lower()
        vendor_lower = vendor.lower()
        
        # Find vendor mentions
        vendor_mentions = [
            sent for sent in text_lower.split('.') 
            if vendor_lower in sent
        ]
        
        if not vendor_mentions:
            return "NOT_MENTIONED"
        
        # Carve-out signals
        carveout_signals = [
            'relies on', 'uses', 'hosted by', 'leverages', 
            'utilizes', 'depends on', 'third-party'
        ]
        
        # Inclusive signals
        inclusive_signals = [
            'manages', 'oversees', 'controls', 'tests', 
            'audits', 'monitors', 'asserts'
        ]
        
        carveout_score = sum(
            1 for signal in carveout_signals 
            if signal in ' '.join(vendor_mentions)
        )
        
        inclusive_score = sum(
            1 for signal in inclusive_signals 
            if signal in ' '.join(vendor_mentions)
        )
        
        if inclusive_score > carveout_score:
            return "INCLUSIVE"
        elif carveout_score > 0:
            return "CARVE-OUT"
        else:
            return "UNDETERMINED"
    
    def cross_reference_controls(self, 
                                  subservices: List[Dict], 
                                  controls_file: str = "controls.xlsx") -> Dict:
        """
        Cross-reference identified subservices with control matrix
        to validate monitoring controls exist (CC9.2)
        """
        if not os.path.exists(controls_file):
            return {"validation": "CONTROLS_FILE_NOT_FOUND"}
        
        df = pd.read_excel(controls_file)
        
        validation_results = []
        for subservice in subservices:
            vendor_name = subservice.get("name", "")
            method = subservice.get("method", "")
            
            if method == "CARVE-OUT":
                # Search for monitoring control
                monitoring_control_found = df[
                    df.apply(
                        lambda row: vendor_name.lower() in str(row).lower() and
                                   ('review' in str(row).lower() or 'soc 2' in str(row).lower()),
                        axis=1
                    )
                ]
                
                validation_results.append({
                    "vendor": vendor_name,
                    "monitoring_control_exists": len(monitoring_control_found) > 0,
                    "control_refs": monitoring_control_found['Control Ref'].tolist() 
                                   if len(monitoring_control_found) > 0 else [],
                    "deficiency": "Missing CC9.2 vendor monitoring control" 
                                 if len(monitoring_control_found) == 0 else None
                })
        
        return {"vendor_monitoring_validation": validation_results}


def main():
    print("=" * 70)
    print("MODULE 1: SOC 2 SCOPE ASSESSMENT ENGINE")
    print("=" * 70)
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: Set OPENAI_API_KEY environment variable")
        print("   export OPENAI_API_KEY='sk-...'\n")
        return
    
    # Initialize assessor
    assessor = ScopeAssessor(api_key)
    
    # Load vector knowledge base
    if not assessor.load_knowledge_base():
        return
    
    # Load system description
    if not os.path.exists(SYSTEM_DESC_FILE):
        print(f"❌ System description not found: {SYSTEM_DESC_FILE}")
        print("\nCreating example file...")
        
        example_text = """
Acme Cloud Services System Description

1. OVERVIEW
Acme provides cloud-based project management software to enterprise clients.

2. INFRASTRUCTURE
Acme relies on Amazon Web Services (AWS) for compute infrastructure, database hosting,
and object storage. AWS is responsible for physical security of data centers.

3. IDENTITY MANAGEMENT  
Acme uses Okta for single sign-on (SSO) and multi-factor authentication (MFA).
User provisioning is managed through Okta's identity lifecycle management.

4. PAYMENT PROCESSING
Stripe is used for payment processing. Stripe handles all credit card data and
maintains PCI-DSS compliance independently.

5. COLLABORATION
The company uses Slack (hosted by Slack Technologies) and Google Workspace for
internal communications and document storage.

6. MONITORING
The Compliance Team reviews SOC 2 Type 2 reports from AWS, Slack, and Google 
Workspace on an annual basis to assess control effectiveness.
"""
        
        with open(SYSTEM_DESC_FILE, 'w') as f:
            f.write(example_text)
        print(f"✅ Created example: {SYSTEM_DESC_FILE}")
    
    with open(SYSTEM_DESC_FILE, 'r') as f:
        system_text = f.read()
    
    print(f"\n📄 Loaded system description ({len(system_text)} chars)")
    print("\n🔍 Analyzing scope with AI auditor persona...\n")
    
    # Run scope assessment
    results = assessor.analyze_system_description(system_text)
    
    # Cross-reference with controls
    if "subservice_organizations" in results:
        validation = assessor.cross_reference_controls(
            results["subservice_organizations"]
        )
        results["control_validation"] = validation
    
    # Save results
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("=" * 70)
    print("SCOPE ASSESSMENT RESULTS")
    print("=" * 70)
    print(json.dumps(results, indent=2))
    print(f"\n✅ Results saved to: {OUTPUT_FILE}")
    
    # Summary
    if "subservice_organizations" in results:
        print("\n📊 SUBSERVICE SUMMARY:")
        for vendor in results["subservice_organizations"]:
            print(f"   • {vendor['name']}: {vendor['method']}")
    
    if "user_entity_controls" in results:
        print(f"\n⚠️  USER ENTITY CONTROLS REQUIRED: {len(results['user_entity_controls'])}")


if __name__ == "__main__":
    main()