"""
retrieval/hybrid_retriever.py
Orchestrates BM25 + Dense Embedding + Reranker into a unified RAG pipeline.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from knowledge.loader import KnowledgeBase, KnowledgeDocument
from retrieval.bm25_retriever import BM25Retriever
from retrieval.embedding_retriever import EmbeddingRetriever
from retrieval.reranker import Reranker

logger = logging.getLogger(__name__)

RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")  # bm25_only | dense_only | hybrid
QUERY_EXPANSION_ENABLED = os.getenv("QUERY_EXPANSION_ENABLED", "true").lower() == "true"


@dataclass
class RetrievalResult:
    """A retrieved knowledge document with relevance score."""
    document: KnowledgeDocument
    score: float
    source: str  # "bm25", "dense", "hybrid", "reranked"


class HybridRetriever:
    """
    Hybrid retrieval pipeline: BM25 (sparse) + BGE Embedding (dense) + Reranker.

    Modes:
    - bm25_only: Only BM25 keyword search
    - dense_only: Only dense embedding search
    - hybrid: BM25 + Dense with Reciprocal Rank Fusion, then rerank
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase | None = None,
        mode: str = RETRIEVAL_MODE,
        use_reranker: bool = True,
        llm_router=None,
    ):
        self._kb = knowledge_base
        self._mode = mode
        self._use_reranker = use_reranker
        self._llm_router = llm_router
        self._bm25 = BM25Retriever()
        self._embedding = EmbeddingRetriever()
        self._reranker = Reranker() if use_reranker else None
        self._documents: list[KnowledgeDocument] = []
        self._doc_texts: list[str] = []
        self._document_positions: dict[str, int] = {}
        self._indexed = False

    def build_index(self, knowledge_base: KnowledgeBase | None = None) -> None:
        """Build retrieval indices from knowledge base."""
        kb = knowledge_base or self._kb
        if kb is None:
            logger.warning("[HybridRetriever] No knowledge base provided")
            return

        kb.load()
        self._kb = kb
        self._documents = kb.get_all_documents()
        self._doc_texts = [doc.full_text for doc in self._documents]
        self._document_positions = {
            str(document.id): index
            for index, document in enumerate(self._documents)
        }

        if not self._doc_texts:
            logger.warning("[HybridRetriever] No documents to index")
            return

        # Build BM25 index
        if self._mode in ("bm25_only", "hybrid"):
            self._bm25.build_index(self._doc_texts)

        # Build embedding index
        if self._mode in ("dense_only", "hybrid"):
            self._embedding.build_index(self._doc_texts)

        self._indexed = True
        logger.info(
            f"[HybridRetriever] Indexed {len(self._documents)} docs, mode={self._mode}"
        )

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def _expand_query_simple(self, query: str) -> list[str]:
        """Simple Vietnamese financial synonym expansion as fallback."""
        expansions = {
            "doanh thu": ["doanh thu thuần", "net sales", "revenue", "tổng doanh thu"],
            "lợi nhuận": ["lợi nhuận sau thuế", "lợi nhuận trước thuế", "net profit", "profit"],
            "tài sản": ["tổng tài sản", "assets", "total assets"],
            "nợ": ["nợ phải trả", "liabilities", "total liabilities"],
            "vốn": ["vốn chủ sở hữu", "equity", "shareholders equity"],
            "tỷ số": ["tỷ lệ", "ratio", "tỷ suất"],
            "p/e": ["p/e ratio", "price to earnings", "trailing pe"],
            "roe": ["return on equity", "tỷ suất lợi nhuận trên vốn"],
            "roa": ["return on assets", "tỷ suất lợi nhuận trên tài sản"],
            "cổ tức": ["cổ tức tiền mặt", "cổ tức cổ phiếu", "dividend"],
            "chi phí": ["chi phí hoạt động", "operating expenses", "opex"],
        }
        q_lower = query.lower()
        expanded = [query]
        for key, synonyms in expansions.items():
            if key in q_lower:
                for syn in synonyms:
                    if syn not in expanded and syn not in q_lower:
                        expanded.append(syn)
        return expanded[:5]

    def _expand_query_llm(self, query: str) -> list[str]:
        """Expand query using LLM for better retrieval."""
        if not self._llm_router:
            return []
        try:
            system = (
                "Bạn là chuyên gia tìm kiếm thông tin tài chính. "
                "Tạo 2-3 biến thể của câu hỏi sau để tăng khả năng tìm kiếm trong knowledge base. "
                "Mỗi biến thể ngắn gọn, khác wording nhưng cùng nghĩa. "
                "Trả về danh sách JSON đơn giản, không giải thích."
            )
            prompt = f"Câu hỏi gốc: {query}\n\nTạo 2-3 biến thể tìm kiếm:"
            response = self._llm_router.generate_for_task(
                prompt, system, task_type="general", max_tokens=200
            )
            text = response.text.strip()
            if text.startswith("[") and text.endswith("]"):
                import json
                variants = json.loads(text)
                if isinstance(variants, list) and all(isinstance(v, str) for v in variants):
                    return variants[:3]
        except Exception as e:
            logger.debug(f"[HybridRetriever] LLM query expansion failed: {e}")
        return []

    def _get_query_variants(self, query: str) -> list[str]:
        """Get query variants using LLM expansion + simple fallback."""
        variants = [query]
        if QUERY_EXPANSION_ENABLED:
            llm_variants = self._expand_query_llm(query)
            variants.extend(llm_variants)
            if len(variants) < 3:
                simple_variants = self._expand_query_simple(query)
                for v in simple_variants:
                    if v not in variants:
                        variants.append(v)
        return variants[:5]

    def _reciprocal_rank_fusion(
        self,
        bm25_indices: list[tuple[int, float]],
        dense_indices: list[tuple[int, float]],
        k: int = 60,
    ) -> list[tuple[int, float]]:
        """Merge BM25 and Dense results using Reciprocal Rank Fusion."""
        rrf_scores: dict[int, float] = {}

        for rank, (idx, _) in enumerate(bm25_indices):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (k + rank + 1)

        for rank, (idx, _) in enumerate(dense_indices):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (k + rank + 1)

        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results

    def _multi_query_search(
        self,
        query: str,
        top_k: int = 5,
        variants: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Fuse query variants by rank while preserving document identity."""
        variants = variants or self._get_query_variants(query)
        if len(variants) <= 1:
            return self._search_and_rerank(query, top_k=top_k)

        doc_scores: dict[int, float] = {}

        for variant in variants:
            results = self._search_raw(variant, top_k=top_k * 2)
            for rank, result in enumerate(results):
                # ids are strings (for example ``financial_terms_12``), not
                # list positions.  Raw scores from different retrievers are
                # incomparable, so apply RRF across the variants instead.
                idx = self._document_positions.get(str(result.document.id))
                if idx is not None:
                    doc_scores[idx] = doc_scores.get(idx, 0.0) + 1.0 / (60 + rank + 1)

        candidates = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        return self._rerank_candidates(query, candidates, top_k, source="multi_query")

    def _rerank_candidates(
        self,
        query: str,
        candidate_indices: list[tuple[int, float]],
        top_k: int,
        source: str,
    ) -> list[RetrievalResult]:
        """Rerank a bounded candidate set, retaining fusion as a fallback."""
        if not candidate_indices:
            return []
        if self._use_reranker and self._reranker is not None and len(candidate_indices) > 1:
            rerank_indices = [idx for idx, _ in candidate_indices[: top_k * 4]]
            reranked = self._reranker.rerank(
                query, [self._doc_texts[idx] for idx in rerank_indices], rerank_indices, top_k
            )
            return [
                RetrievalResult(document=self._documents[item.doc_index], score=item.score, source="reranked")
                for item in reranked
                if 0 <= item.doc_index < len(self._documents)
            ]
        return [
            RetrievalResult(document=self._documents[idx], score=score, source=source)
            for idx, score in candidate_indices[:top_k]
            if 0 <= idx < len(self._documents)
        ]

    def _search_and_rerank(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Run the single-query flow without expanding the query again."""
        raw_results = self._search_raw(query, top_k=top_k * 3)
        candidates = [
            (self._document_positions[str(item.document.id)], item.score)
            for item in raw_results
            if str(item.document.id) in self._document_positions
        ]
        source = raw_results[0].source if raw_results else "hybrid"
        return self._rerank_candidates(query, candidates, top_k, source)

    def _search_raw(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        """Raw search without multi-query or reranking."""
        if not self._indexed or not self._documents:
            return []

        candidate_indices: list[tuple[int, float]] = []

        if self._mode == "bm25_only":
            bm25_results = self._bm25.search(query, top_k=top_k * 2)
            candidate_indices = [(r.doc_index, r.score) for r in bm25_results]

        elif self._mode == "dense_only":
            dense_results = self._embedding.search(query, top_k=top_k * 2)
            candidate_indices = [(r.doc_index, r.score) for r in dense_results]

        else:  # hybrid
            bm25_results = self._bm25.search(query, top_k=top_k * 3)
            dense_results = self._embedding.search(query, top_k=top_k * 3)
            bm25_pairs = [(r.doc_index, r.score) for r in bm25_results]
            dense_pairs = [(r.doc_index, r.score) for r in dense_results]
            candidate_indices = self._reciprocal_rank_fusion(bm25_pairs, dense_pairs)

        return [
            RetrievalResult(
                document=self._documents[idx],
                score=score,
                source="hybrid",
            )
            for idx, score in candidate_indices[:top_k]
            if idx < len(self._documents)
        ]

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """
        Search knowledge base using configured retrieval mode.

        Uses multi-query expansion if enabled, then hybrid retrieval + reranking.
        """
        if not self._indexed or not self._documents:
            if self._kb:
                docs = self._kb.search_simple(query, top_k)
                return [
                    RetrievalResult(document=d, score=1.0, source="keyword_fallback")
                    for d in docs
                ]
            return []

        # Generate variants once.  The old path generated them twice and the
        # multi-query branch then converted string ids into list positions.
        variants = self._get_query_variants(query) if QUERY_EXPANSION_ENABLED else [query]
        if len(variants) > 1:
            return self._multi_query_search(query, top_k, variants)
        return self._search_and_rerank(query, top_k)

        # Standard hybrid search
        candidate_indices: list[tuple[int, float]] = []

        if self._mode == "bm25_only":
            bm25_results = self._bm25.search(query, top_k=top_k * 2)
            candidate_indices = [(r.doc_index, r.score) for r in bm25_results]
            source = "bm25"

        elif self._mode == "dense_only":
            dense_results = self._embedding.search(query, top_k=top_k * 2)
            candidate_indices = [(r.doc_index, r.score) for r in dense_results]
            source = "dense"

        else:  # hybrid
            bm25_results = self._bm25.search(query, top_k=top_k * 3)
            dense_results = self._embedding.search(query, top_k=top_k * 3)

            bm25_pairs = [(r.doc_index, r.score) for r in bm25_results]
            dense_pairs = [(r.doc_index, r.score) for r in dense_results]

            candidate_indices = self._reciprocal_rank_fusion(bm25_pairs, dense_pairs)
            source = "hybrid"

        if not candidate_indices:
            return []

        # Rerank top candidates
        if self._use_reranker and self._reranker is not None and len(candidate_indices) > top_k:
            rerank_indices = [idx for idx, _ in candidate_indices[:top_k * 2]]
            rerank_texts = [self._doc_texts[idx] for idx in rerank_indices]

            reranked = self._reranker.rerank(query, rerank_texts, rerank_indices, top_k)
            return [
                RetrievalResult(
                    document=self._documents[r.doc_index],
                    score=r.score,
                    source="reranked",
                )
                for r in reranked
                if r.doc_index < len(self._documents)
            ]

        # No reranker — return top_k from fusion
        return [
            RetrievalResult(
                document=self._documents[idx],
                score=score,
                source=source,
            )
            for idx, score in candidate_indices[:top_k]
            if idx < len(self._documents)
        ]

    def stats(self) -> dict:
        return {
            "indexed": self._indexed,
            "mode": self._mode,
            "total_documents": len(self._documents),
            "bm25_ready": self._bm25.is_indexed,
            "embedding_ready": self._embedding.is_indexed,
            "reranker_enabled": self._use_reranker,
        }
