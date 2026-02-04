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
    parser = argparse.ArgumentParser(description="Ingestia wielu plików PDF do bazy wektorowej.")
    parser.add_argument("--docs_dir", type=str, default=".", help="Folder z plikami PDF (domyślnie obecny katalog).")
    parser.add_argument("--output_dir", type=str, default="soc2_vector_index", help="Folder wyjściowy indeksu.")

    args = parser.parse_args()

    # Lista plików PDF do przetworzenia
    pdf_files = [f for f in os.listdir(args.docs_dir) if f.lower().endswith('.pdf')]

    if not pdf_files:
        print(f"❌ Nie znaleziono plików PDF w katalogu '{args.docs_dir}'.")
        return

    print(f"--- ROZPOCZYNAM TWORZENIE BAZY WIEDZY Z {len(pdf_files)} PLIKÓW ---")

    all_documents = []

    # 1. Wczytywanie wszystkich PDF-ów
    for pdf_file in pdf_files:
        path = os.path.join(args.docs_dir, pdf_file)
        print(f" -> Wczytywanie: {pdf_file}...")
        try:
            loader = PyPDFLoader(path)
            docs = loader.load()
            # Dodajemy metadane źródłowe (żeby wiedzieć z którego pliku pochodzi wiedza)
            for doc in docs:
                doc.metadata['source_file'] = pdf_file
            all_documents.extend(docs)
        except Exception as e:
            print(f"⚠️ Błąd przy pliku {pdf_file}: {e}")

    print(f"✅ Łącznie wczytano {len(all_documents)} stron dokumentacji.")

    # 2. Chunking (Dzielenie na fragmenty)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(all_documents)
    print(f"✅ Utworzono {len(chunks)} fragmentów wiedzy.")

    # 3. Wektoryzacja
    print("-> Generowanie wektorów (OpenAI Embeddings)...")
    try:
        embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
        vector_store = FAISS.from_documents(chunks, embeddings)

        # 4. Zapis
        vector_store.save_local(args.output_dir)
        print(f"✅ SUKCES! Kompletna baza wiedzy zapisana w '{args.output_dir}'.")
        print("   Baza zawiera wiedzę z plików:", ", ".join(pdf_files))

    except Exception as e:
        print(f"❌ Błąd API OpenAI lub FAISS: {e}")

if __name__ == "__main__":
    main()