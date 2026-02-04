import pandas as pd
from openai import OpenAI
import json
import os
import time
import sys
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import OPENAI_API_KEY

sys.stdout.reconfigure(encoding='utf-8')


client = OpenAI(api_key=OPENAI_API_KEY)
INPUT_FILE = "none_ex_files/sanitized_controls.xlsx"
OUTPUT_FILE = "none_ex_files/mapped_controls_rag.xlsx"
INDEX_PATH = "soc2_vector_index"

def load_knowledge_base():
    if not os.path.exists(INDEX_PATH): raise FileNotFoundError("Run 'prepare_vectors.py' first.")
    embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
    return FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)

def query_tsc_context(vector_store, query_text):
    docs = vector_store.similarity_search(query_text, k=3)
    return "\n\n---\n\n".join([d.page_content for d in docs])

def map_control_with_rag(control_text, context_from_pdf):
    system_prompt = """
    You are a CISA Auditor. Analyze the control against AICPA SOC 2 standards.
    Use the provided PDF context as the source of truth.
    
    TASK:
    1. Identify the TSC Criteria Code (e.g., CC6.1, A1.2).
    2. Identify the specific "Point of Focus" addressed.
    3. Provide a Rationale in English.

    Return JSON:
    {
      "tsc_code": "Code",
      "point_of_focus": "Text from PDF",
      "rationale": "Explanation in English"
    }
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": f"CONTROL: {control_text}\nCONTEXT: {context_from_pdf}"}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except: return {}

def main():
    if not os.path.exists(INPUT_FILE): return
    print("--- MODULE 2: MAPPER RAG (ENGLISH) ---")
    kb = load_knowledge_base()
    df = pd.read_excel(INPUT_FILE)

    mapped_data = []
    # Teraz szukamy konkretnej kolumny, którą stworzył sanitizer
    target_col = "Sanitized Control Description"

    if target_col not in df.columns:
        print(f"Error: Column '{target_col}' not found. Check sanitizer output.")
        return

    for idx, row in df.iterrows():
        text = row.get(target_col)
        if not text: continue

        print(f" -> Mapping control row {idx+1}...")
        context = query_tsc_context(kb, str(text))
        mapping = map_control_with_rag(str(text), context)

        mapped_data.append({
            "Control Ref": row.get("Control Ref", idx),
            "Sanitized Control": text,
            "Mapped TSC": mapping.get("tsc_code"),
            "Point of Focus": mapping.get("point_of_focus"),
            "Rationale": mapping.get("rationale")
        })
        time.sleep(0.5)

    pd.DataFrame(mapped_data).to_excel(OUTPUT_FILE, index=False)
    print(f"✅ Mapped file saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()