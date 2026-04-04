import os
import argparse
import sys
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import OPENAI_API_KEY, SOC2_MODEL

sys.stdout.reconfigure(encoding='utf-8')

# Filename keyword filters used to route PDFs into the correct domain index.
_SSAE21_KEYWORDS = ("ssae", "standards", "attestation")
_TSC_KEYWORDS = ("tsc", "criteria", "trust")

# Legacy monolithic index name kept for backward-compatibility with Phase 4.2.
_LEGACY_INDEX = "soc2_vector_index"


def _classify_pdf(filename: str):
    """
    Return the domain bucket for *filename*.

    Returns
    -------
    'ssae21' | 'tsc' | 'default'
    """
    lower = filename.lower()
    if any(kw in lower for kw in _SSAE21_KEYWORDS):
        return "ssae21"
    if any(kw in lower for kw in _TSC_KEYWORDS):
        return "tsc"
    return "default"


def _load_pdfs(docs_dir: str, pdf_files: list) -> list:
    """Load and tag all PDFs; return a list of LangChain Document objects."""
    all_documents = []
    for pdf_file in pdf_files:
        path = os.path.join(docs_dir, pdf_file)
        print(f" -> Loading: {pdf_file}...")
        try:
            loader = PyPDFLoader(path)
            docs = loader.load()
            for doc in docs:
                doc.metadata["source_file"] = pdf_file
            all_documents.extend(docs)
        except Exception as e:
            print(f"⚠️ Error processing {pdf_file}: {e}")
    return all_documents


def _build_and_save_index(chunks: list, embeddings, output_dir: str, label: str):
    """Build a FAISS index from *chunks* and persist it to *output_dir*."""
    if not chunks:
        print(f"⚠️  No chunks for '{label}' index – skipping.")
        return
    print(f"   -> Building '{label}' index from {len(chunks)} chunks...")
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(output_dir)
    print(f"   ✅ '{label}' index saved to '{output_dir}'.")


def main():
    parser = argparse.ArgumentParser(description="Process PDF files into domain-specific vector indices.")
    parser.add_argument("--docs_dir", type=str, default="pdf_docs",
                        help="Folder with PDF files (default: pdf_docs/).")
    parser.add_argument("--output_dir", type=str, default=_LEGACY_INDEX,
                        help="Output directory for the legacy monolithic index (default: soc2_vector_index).")
    parser.add_argument("--ssae21_dir", type=str, default="vector_index_ssae21",
                        help="Output directory for the SSAE 21 domain index.")
    parser.add_argument("--tsc_dir", type=str, default="vector_index_tsc",
                        help="Output directory for the Trust Services Criteria domain index.")

    args = parser.parse_args()

    # List PDF files to process
    pdf_files = [f for f in os.listdir(args.docs_dir) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print(f"❌ No PDF files found in directory '{args.docs_dir}'.")
        print(f"   Place your SOC 2 documentation PDFs in the '{args.docs_dir}/' directory.")
        return

    print(f"--- CREATING KNOWLEDGE BASES FROM {len(pdf_files)} PDF FILES ---")

    # 1. Load all PDFs
    all_documents = _load_pdfs(args.docs_dir, pdf_files)
    print(f"✅ Loaded {len(all_documents)} pages of documentation.")

    # 2. Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    all_chunks = text_splitter.split_documents(all_documents)
    print(f"✅ Created {len(all_chunks)} knowledge chunks total.")

    # 3. Route chunks into domain buckets
    ssae21_chunks = []
    tsc_chunks = []
    default_chunks = []

    for chunk in all_chunks:
        bucket = _classify_pdf(chunk.metadata.get("source_file", ""))
        if bucket == "ssae21":
            ssae21_chunks.append(chunk)
        elif bucket == "tsc":
            tsc_chunks.append(chunk)
        else:
            default_chunks.append(chunk)

    print(f"\n   Domain routing results:")
    print(f"   - SSAE 21 chunks    : {len(ssae21_chunks)}")
    print(f"   - TSC chunks        : {len(tsc_chunks)}")
    print(f"   - Unclassified chunks: {len(default_chunks)}")

    # 4. Generate vector embeddings and save all indices
    print("\n-> Generating vectors (OpenAI Embeddings)...")
    try:
        embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

        # Domain-specific indices (used by Phases 1-3)
        _build_and_save_index(ssae21_chunks, embeddings, args.ssae21_dir, "vector_index_ssae21")
        _build_and_save_index(tsc_chunks, embeddings, args.tsc_dir, "vector_index_tsc")

        # Legacy monolithic index (used by Phase 4.2 modul_2_mapper_rag.py)
        _build_and_save_index(all_chunks, embeddings, args.output_dir, _LEGACY_INDEX)

        print(f"\n✅ SUCCESS! All knowledge bases built.")
        print("   PDFs processed:", ", ".join(pdf_files))

    except Exception as e:
        print(f"❌ OpenAI API or FAISS error: {e}")

if __name__ == "__main__":
    main()