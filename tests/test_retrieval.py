import unittest

from knowledge.loader import KnowledgeDocument
from retrieval.hybrid_retriever import HybridRetriever, RetrievalResult


class TestHybridRetriever(unittest.TestCase):
    def test_multi_query_preserves_document_identity(self):
        retriever = HybridRetriever(mode="bm25_only", use_reranker=False)
        retriever._documents = [
            KnowledgeDocument(id="financial_terms_12", title="A", content="a", category="x", source_file="x"),
            KnowledgeDocument(id="economics_99", title="B", content="b", category="x", source_file="x"),
        ]
        retriever._doc_texts = ["a", "b"]
        retriever._document_positions = {"financial_terms_12": 0, "economics_99": 1}
        retriever._indexed = True

        def fake_search(query, top_k=10):
            doc = retriever._documents[1 if query == "variant" else 0]
            return [RetrievalResult(document=doc, score=1.0, source="hybrid")]

        retriever._search_raw = fake_search
        results = retriever._multi_query_search("original", top_k=2, variants=["original", "variant"])

        self.assertEqual({item.document.id for item in results}, {"financial_terms_12", "economics_99"})
