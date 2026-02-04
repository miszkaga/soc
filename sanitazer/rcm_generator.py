import json

SCOPE_STRATEGY_FILE = "scope_strategy.json"


def load_scope_strategy():
    try:
        with open(SCOPE_STRATEGY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def generate_controls_from_desc(desc, scope_strategy=None):
    system_prompt = "Generating controls based on description."  # Placeholder for actual prompt logic

    if scope_strategy:
        if scope_strategy.get('method') == 'CARVE_OUT':
            vendors = ', '.join(scope_strategy.get('vendors', []))
            system_prompt += f"\nSCOPE CONTEXT: The system uses CARVE_OUT method for the following vendors: [{vendors}]. You MUST generate CC9.2 monitoring controls for each vendor that includes annual SOC 2 report review."
        if 'required_controls' in scope_strategy:
            required_controls = ', '.join(scope_strategy['required_controls'])
            system_prompt += f"\nYou must include the following controls: [{required_controls}]."
    
    # Continue with existing control generation logic here


def main():
    scope_strategy = load_scope_strategy()
    if scope_strategy:
        print("Scope-aware mode is active.")
    else:
        print("Scope-aware mode is not active.")
    
    # Your existing main logic here
    # Call generate_controls_from_desc with scope_strategy if needed
    
client = OpenAI(api_key=OPENAI_API_KEY)  # Keep existing client initialization intact
