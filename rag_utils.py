"""
Shared RAG utility module for domain-specific vector index loading and querying.

Each pipeline phase loads only the vector index it requires:
  - vector_index_ssae21  : SSAE 21 attestation-standards chunks (Phases 1 & 3)
  - vector_index_tsc     : AICPA Trust Services Criteria chunks  (Phase 2)

If an index is not present on disk the caller receives a FileNotFoundError and
is expected to fall back to prompt-only behaviour.
"""

import os
import warnings

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import OPENAI_API_KEY


def load_specific_knowledge_base(index_name: str):
    """
    Load the requested FAISS vector index from disk.

    Parameters
    ----------
    index_name : str
        Directory name of the FAISS index (e.g. 'vector_index_ssae21').

    Returns
    -------
    FAISS vector store ready for similarity search.

    Raises
    ------
    FileNotFoundError
        If the index directory does not exist.  Callers should catch this and
        fall back to non-RAG behaviour, logging a warning to run
        prepare_vectors.py.
    """
    if not os.path.exists(index_name):
        raise FileNotFoundError(
            f"Vector index '{index_name}' not found. "
            f"Run prepare_vectors.py to build the required indices."
        )

    embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
    return FAISS.load_local(index_name, embeddings, allow_dangerous_deserialization=True)


def get_phase_context(vector_store, query_text: str, k: int = 3) -> str:
    """
    Retrieve the top-k most relevant context chunks for *query_text*.

    Parameters
    ----------
    vector_store : FAISS
        A loaded FAISS knowledge base returned by load_specific_knowledge_base.
    query_text : str
        The natural-language query to embed and search against the index.
    k : int
        Number of chunks to retrieve (default: 3).

    Returns
    -------
    str
        The retrieved chunks joined by a separator, ready to be injected into
        an LLM prompt.
    """
    docs = vector_store.similarity_search(query_text, k=k)
    return "\n\n---\n\n".join([d.page_content for d in docs])
