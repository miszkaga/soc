import os
import argparse
import sys
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import OPENAI_API_KEY, SOC2_MODEL

sys.stdout.reconfigure(encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="Process multiple PDF files into vector database.")
    parser.add_argument("--docs_dir", type=str, default="pdf_docs", help="Folder with PDF files (default: pdf_docs/).")
    parser.add_argument("--output_dir", type=str, default="soc2_vector_index", help="Output directory for vector index.")

    args = parser.parse_args()

    # Lista plików PDF do przetworzenia
    pdf_files = [f for f in os.listdir(args.docs_dir) if f.lower().endswith('.pdf')]

    if not pdf_files:
        print(f"❌ No PDF files found in directory '{args.docs_dir}'.")
        print(f"   Place your SOC 2 documentation PDFs in the '{args.docs_dir}/' directory.")
        return

    print(f"--- CREATING KNOWLEDGE BASE FROM {len(pdf_files)} PDF FILES ---")

    all_documents = []

    # 1. Wczytywanie wszystkich PDF-ów
    for pdf_file in pdf_files:
        path = os.path.join(args.docs_dir, pdf_file)
        print(f" -> Loading: {pdf_file}...")
        try:
            loader = PyPDFLoader(path)
            docs = loader.load()
            # Dodajemy metadane źródłowe (żeby wiedzieć z którego pliku pochodzi wiedza)
            for doc in docs:
                doc.metadata['source_file'] = pdf_file
            all_documents.extend(docs)
        except Exception as e:
            print(f"⚠️ Error processing {pdf_file}: {e}")

    print(f"✅ Loaded {len(all_documents)} pages of documentation.")

    # 2. Chunking (Dzielenie na fragmenty)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(all_documents)
    print(f"✅ Created {len(chunks)} knowledge chunks.")

    # 3. Wektoryzacja
    print("-> Generating vectors (OpenAI Embeddings)...")
    try:
        embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
        vector_store = FAISS.from_documents(chunks, embeddings)

        # 4. Zapis
        vector_store.save_local(args.output_dir)
        print(f"✅ SUCCESS! Complete knowledge base saved in '{args.output_dir}'.")
        print("   Knowledge base contains data from files:", ", ".join(pdf_files))

    except Exception as e:
        print(f"❌ OpenAI API or FAISS error: {e}")

if __name__ == "__main__":
    main()