import pandas as pd
from openai import OpenAI
import json
import os

client = OpenAI(api_key="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")
INPUT_FILE = "controls.xlsx"
OUTPUT_FILE = "sanitized_controls.xlsx"
MAP_FILE = "sensitive_map.json"

def smart_detect_column(df):
    """Detects description column."""
    text_cols = df.select_dtypes(include=['object', 'string']).columns.tolist()
    best_col = None
    max_score = -100
    keywords = ['description', 'activity', 'control', 'narrative']

    for col in text_cols:
        score = 0
        if any(key in col.lower() for key in keywords): score += 50
        sample = df[col].dropna().astype(str).tolist()
        if sample:
            avg_len = sum(len(t) for t in sample) / len(sample)
            if avg_len > 30: score += avg_len * 0.5
        if score > max_score:
            max_score = score
            best_col = col
    return best_col

def generate_map_with_ai(text_sample):
    """English prompt for sanitization."""
    system_prompt = """
    You are a Data Privacy Expert. Create a sanitization map (JSON) for SOC 2 audit data.
    
    TOKEN CATEGORIES (Use these English tokens):
    1. [ORGANIZATION] - Name of the audited company.
    2. [VENDOR] - External service providers (AWS, Azure, Jira, Slack, GitHub).
    3. [INTERNAL_SYSTEM] - Internal app names, databases (ProdDB, CoreApp).
    4. [ROLE] or [PERSON] - Names/Titles (e.g., "John Doe" -> "[ROLE]" if context implies role).
    5. [LOCATION] - Physical locations (e.g., "New York DC").
    
    CRITICAL RULES (DO NOT SANITIZE):
    - Do NOT sanitize frequencies (daily, quarterly, annually) - required for sampling.
    - Do NOT sanitize generic tech terms (VPN, MFA, SQL, Antivirus).
    
    Return pure JSON object: {"Sensitive Phrase": "[TOKEN]"}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            response_format={ "type": "json_object" },
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": text_sample}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"API Error: {e}")
        return {}

def apply_sanitization(text, mapping):
    if not isinstance(text, str): return str(text)
    clean = text
    for phrase in sorted(mapping.keys(), key=len, reverse=True):
        clean = clean.replace(phrase, mapping[phrase])
    return clean

def main():
    if not os.path.exists(INPUT_FILE): return
    print("--- MODULE 1: SANITIZER (ENGLISH) ---")
    df = pd.read_excel(INPUT_FILE)
    target_col = smart_detect_column(df)
    print(f"Detected column: {target_col}")

    sample_text = "\n".join(df[target_col].dropna().astype(str).unique().tolist()[:50])
    sensitive_map = generate_map_with_ai(sample_text)

    with open(MAP_FILE, 'w') as f: json.dump(sensitive_map, f, indent=4)

    # Zapiszemy pod ujednoliconą nazwą kolumny dla wygody kolejnych modułów
    df['Sanitized Control Description'] = df[target_col].apply(lambda x: apply_sanitization(x, sensitive_map))
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"✅ Sanitized file saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()