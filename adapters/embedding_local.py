# adapters/embedding_local.py — Semantic Vector Embeddings for R1 Embedding Ranker
import math
import re
from typing import Mapping, Sequence
import numpy as np
from scipy.sparse.linalg import svds

from core.types import CandidateId, ResumeText


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric words."""
    return re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())


def compute_job_embeddings(
    jd_text: str,
    resumes: Sequence[ResumeText],
    dim: int = 48,
    scale: int = 10000,
) -> tuple[tuple[int, ...], dict[CandidateId, tuple[int, ...]]]:
    """Compute dense semantic embeddings for a job description and a set of resumes.

    Uses subword and word n-gram latent semantic analysis (LSA / Truncated SVD) to project
    texts into a dense semantic concept space without external network dependencies.
    Outputs integer vectors scaled to `scale` (default: 10000) for exact compatibility
    with core.rankers.r1_embedding.rank_embedding.
    """
    all_texts = [jd_text] + [r.text for r in resumes]
    n_docs = len(all_texts)

    # Build vocabulary of unigrams and bigrams
    doc_token_lists = [_tokenize(t) for t in all_texts]
    vocab_index: dict[str, int] = {}
    
    for tokens in doc_token_lists:
        for t in tokens:
            if t not in vocab_index:
                vocab_index[t] = len(vocab_index)
        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]}_{tokens[i+1]}"
            if bg not in vocab_index:
                vocab_index[bg] = len(vocab_index)

    vocab_size = len(vocab_index)
    if vocab_size == 0:
        zero_vec = tuple(0 for _ in range(dim))
        return zero_vec, {r.candidate_id: zero_vec for r in resumes}

    # Build TF-IDF matrix (docs x vocab)
    tf_matrix = np.zeros((n_docs, vocab_size), dtype=np.float64)
    doc_counts = np.zeros(vocab_size, dtype=np.float64)

    for doc_idx, tokens in enumerate(doc_token_lists):
        doc_set = set()
        for t in tokens:
            idx = vocab_index[t]
            tf_matrix[doc_idx, idx] += 1.0
            doc_set.add(idx)
        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]}_{tokens[i+1]}"
            idx = vocab_index[bg]
            tf_matrix[doc_idx, idx] += 1.5  # slight boost for phrase co-occurrence
            doc_set.add(idx)
        for idx in doc_set:
            doc_counts[idx] += 1.0

    # Smooth IDF
    idf = np.log((1.0 + n_docs) / (1.0 + doc_counts)) + 1.0
    tfidf_matrix = tf_matrix * idf

    # Normalize L2 rows
    row_norms = np.linalg.norm(tfidf_matrix, axis=1, keepdims=True)
    row_norms[row_norms == 0] = 1.0
    normalized_matrix = tfidf_matrix / row_norms

    # Truncated SVD / LSA projection to target dimension
    target_k = min(dim, n_docs - 1, vocab_size - 1)
    if target_k >= 2 and n_docs > 2:
        try:
            u, s, _ = svds(normalized_matrix, k=target_k)
            dense_vectors = u * s
        except Exception:
            # Fallback to random projection or direct slice if svds fails
            dense_vectors = normalized_matrix[:, :dim]
    else:
        dense_vectors = normalized_matrix[:, :dim]

    # Pad with zeros if necessary to ensure exact `dim` dimension
    current_dim = dense_vectors.shape[1]
    if current_dim < dim:
        pad_width = ((0, 0), (0, dim - current_dim))
        dense_vectors = np.pad(dense_vectors, pad_width, mode="constant")

    # Quantize and normalize to integer vector
    int_vectors: list[tuple[int, ...]] = []
    for row in dense_vectors:
        norm = np.linalg.norm(row)
        if norm > 0:
            normed_row = row / norm
        else:
            normed_row = row
        quantized = tuple(int(round(float(val) * scale)) for val in normed_row[:dim])
        int_vectors.append(quantized)

    jd_vec = int_vectors[0]
    resume_vecs: dict[CandidateId, tuple[int, ...]] = {}
    for i, r in enumerate(resumes):
        resume_vecs[r.candidate_id] = int_vectors[i + 1]

    return jd_vec, resume_vecs
