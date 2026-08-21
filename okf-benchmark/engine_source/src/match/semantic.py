"""
Step 6 (updated): Semantic Match Tier — Hybrid Dense + Sparse Multi-Chunk Retrieval.

Architecture:
  - Dense: One FAISS IndexFlatIP holding 3 × N vectors (opening, body, holding per case).
  - Sparse: Scikit-learn's TfidfVectorizer fitted on the same chunk texts.
  - At search time:
    1. Retrieve top candidates using both dense (embeddings) and sparse (TF-IDF cosine similarities).
    2. Compute the exact dense and sparse scores for the union of top candidates.
    3. Combine scores using: hybrid_score = dense_weight * dense_score + sparse_weight * sparse_score.
    4. Group chunks by CNR and take the MAX hybrid score across chunks.
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import time
import json
import yaml
import numpy as np
import pandas as pd
import faiss
from typing import Dict, Any, List, Optional, Tuple

import torch
torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except Exception:
    pass

from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_semantic_config(config_path: str = "config.yaml") -> dict:
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("semantic_match", {
                "model_name": "all-MiniLM-L6-v2",
                "max_text_chars": 1500,
                "top_k": 5,
                "similarity_threshold": 0.75,
                "hybrid": {"enabled": False, "dense_weight": 0.7, "sparse_weight": 0.3},
            })
    except Exception:
        return {
            "model_name": "all-MiniLM-L6-v2",
            "max_text_chars": 1500,
            "top_k": 5,
            "similarity_threshold": 0.75,
            "hybrid": {"enabled": False, "dense_weight": 0.7, "sparse_weight": 0.3},
        }


# ---------------------------------------------------------------------------
# Text construction helpers
# ---------------------------------------------------------------------------

def construct_case_input_text(rec: Dict[str, Any], max_chars: int = 1500) -> str:
    """Legacy single-snippet text construction (used for query side + fallback)."""
    pet  = str(rec.get("petitioner", "") or "").strip()
    resp = str(rec.get("respondent", "") or "").strip()
    snippet = str(rec.get("extracted_text_snippet", "") or "").strip()
    title   = str(rec.get("title", "") or "").strip()

    parts = []
    if pet or resp:
        parts.append(f"Parties: {pet} v. {resp}")
    elif title:
        parts.append(f"Title: {title}")
    if snippet:
        parts.append(snippet)

    return "\n".join(parts)[:max_chars]


def _get_chunk_texts(rec: Dict[str, Any], max_chars: int = 1500) -> List[Tuple[str, str]]:
    """
    Return list of (chunk_type, text) for a canonical record.

    If the record has chunk columns (added by build_chunks.py) → use them.
    Otherwise fall back to a single snippet (legacy behaviour).
    """
    opening = str(rec.get("chunk_opening") or "").strip()
    body    = str(rec.get("chunk_body")    or "").strip()
    holding = str(rec.get("chunk_holding") or "").strip()

    if opening or body or holding:
        chunks = []
        if opening:
            chunks.append(("opening", opening[:max_chars]))
        if body:
            chunks.append(("body", body[:max_chars]))
        if holding:
            chunks.append(("holding", holding[:max_chars]))
        return chunks

    # Legacy fallback: single snippet
    return [("snippet", construct_case_input_text(rec, max_chars))]


# ---------------------------------------------------------------------------
# SemanticMatcher
# ---------------------------------------------------------------------------

class SemanticMatcher:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_semantic_config(config_path)
        self.model_name          = self.config.get("model_name",          "all-MiniLM-L6-v2")
        self.max_chars           = self.config.get("max_text_chars",      1500)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.75)
        self.top_k               = self.config.get("top_k",               5)

        hybrid_cfg = self.config.get("hybrid", {})
        self.hybrid_enabled = hybrid_cfg.get("enabled", False)
        self.dense_weight   = hybrid_cfg.get("dense_weight", 0.7)
        self.sparse_weight  = hybrid_cfg.get("sparse_weight", 0.3)

        self.model = SentenceTransformer(self.model_name, device="cpu")

        # FAISS index (flat inner-product on L2-normalised vectors = cosine sim)
        self.faiss_index: Optional[faiss.IndexFlatIP] = None
        self.embeddings: Optional[np.ndarray] = None
        
        # Sparse index (TF-IDF Vectorizer + matrix)
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english', sublinear_tf=True)
        self.tfidf_matrix: Optional[Any] = None

        # Parallel metadata for every vector in the indices
        self.index_meta: List[Dict[str, str]] = []   # [{cnr, chunk_type}, ...]
        # One canonical record per unique CNR (for returning matched_record)
        self.cnr_to_record: Dict[str, Dict[str, Any]] = {}
        self.dimension: int = 0

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def build_index(self, canonical_df: pd.DataFrame) -> Tuple[float, float]:
        """
        Embed all chunk texts, build dense FAISS index, and sparse TF-IDF matrix.

        Returns (build_time_seconds, index_memory_size_mb).
        """
        t0 = time.time()

        self.cnr_to_record = {}
        all_texts: List[str]            = []
        all_meta:  List[Dict[str, str]] = []

        for rec in canonical_df.to_dict(orient="records"):
            cnr = str(rec.get("cnr", "") or rec.get("case_number", ""))
            self.cnr_to_record[cnr] = rec

            for chunk_type, text in _get_chunk_texts(rec, self.max_chars):
                if text:
                    all_texts.append(text)
                    all_meta.append({"cnr": cnr, "chunk_type": chunk_type})

        # Dense embedding generation with disk caching
        cache_path = "/tmp/semantic_embeddings_cache.npy"
        if os.path.exists(cache_path):
            self.embeddings = np.load(cache_path)
        else:
            embeddings = self.model.encode(
                all_texts,
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            self.embeddings = np.array(embeddings, dtype=np.float32)
            np.save(cache_path, self.embeddings)

        self.dimension   = self.embeddings.shape[1]
        self.index_meta  = all_meta

        self.faiss_index = faiss.IndexFlatIP(self.dimension)
        self.faiss_index.add(self.embeddings)

        # Sparse TF-IDF generation
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(all_texts)

        build_time    = time.time() - t0
        index_size_mb = (self.embeddings.nbytes + self.tfidf_matrix.data.nbytes) / (1024 * 1024)
        return build_time, index_size_mb

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_rec: Dict[str, Any],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        hybrid_override: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Embed and vectorize query, perform hybrid search, group by CNR and return top-k matches.
        """
        if self.faiss_index is None or self.tfidf_matrix is None:
            raise ValueError("Indices not built. Call build_index() first.")

        k               = top_k    if top_k    is not None else self.top_k
        thresh          = threshold if threshold is not None else self.similarity_threshold
        hybrid_active   = hybrid_override if hybrid_override is not None else self.hybrid_enabled
        fetch_k         = k * 5

        # Query text: treat as single chunk
        query_text = construct_case_input_text(query_rec, self.max_chars)
        if not query_text.strip():
            return []

        # Dense query embedding
        q_emb = self.model.encode([query_text], show_progress_bar=False, normalize_embeddings=True)
        q_emb = np.array(q_emb, dtype=np.float32)

        # Dense search: retrieves top chunks
        dense_scores, dense_indices = self.faiss_index.search(q_emb, min(fetch_k, self.faiss_index.ntotal))
        dense_scores = dense_scores[0]
        dense_indices = dense_indices[0]

        # Sparse search: computes TF-IDF similarities
        query_tfidf = self.tfidf_vectorizer.transform([query_text])
        sparse_all_scores = self.tfidf_matrix.dot(query_tfidf.T).toarray().ravel()

        if hybrid_active:
            sparse_indices = np.argsort(-sparse_all_scores)[:fetch_k]
        else:
            sparse_indices = []

        # Union of dense and sparse candidate chunks
        candidate_indices = set(dense_indices)
        for idx in sparse_indices:
            if sparse_all_scores[idx] > 0.0:
                candidate_indices.add(idx)

        # Remove invalid FAISS indexes
        candidate_indices = {idx for idx in candidate_indices if idx >= 0 and idx < len(self.index_meta)}

        # Score candidates
        cnr_best_score = {}
        cnr_best_chunk_type = {}
        cnr_dense_score = {}
        cnr_sparse_score = {}

        for idx in candidate_indices:
            meta = self.index_meta[idx]
            cnr  = meta["cnr"]

            # Cosine similarity for dense
            dense_score = float(np.dot(q_emb[0], self.embeddings[idx]))
            # Cosine similarity for sparse TF-IDF
            sparse_score = float(sparse_all_scores[idx])

            # Combine scores
            if hybrid_active:
                score = self.dense_weight * dense_score + self.sparse_weight * sparse_score
            else:
                score = dense_score

            if cnr not in cnr_best_score or score > cnr_best_score[cnr]:
                cnr_best_score[cnr] = score
                cnr_best_chunk_type[cnr] = meta["chunk_type"]
                cnr_dense_score[cnr] = dense_score
                cnr_sparse_score[cnr] = sparse_score

        # Sort by hybrid/dense score descending, take top_k
        ranked = sorted(cnr_best_score.items(), key=lambda x: -x[1])[:k]

        results = []
        for cnr, score in ranked:
            candidate = self.cnr_to_record.get(cnr, {})
            is_match  = score >= thresh
            results.append({
                "matched":         is_match,
                "match_tier":      "semantic",
                "matched_on":      "hybrid_similarity" if hybrid_active else "embedding_similarity",
                "best_chunk_type": cnr_best_chunk_type[cnr],
                "confidence":      round(score, 4),
                "similarity_score": score,
                "dense_score":     round(cnr_dense_score[cnr], 4),
                "sparse_score":    round(cnr_sparse_score[cnr], 4),
                "matched_case_id": candidate.get("cnr", "") or candidate.get("case_number", ""),
                "matched_record":  candidate,
            })

        return results
