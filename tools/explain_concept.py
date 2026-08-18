"""
tools/explain_concept.py
Concept explanation tool — explains financial terms using RAG + LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class ExplainConceptTool(Tool):
    """Explain financial concepts, terms, and formulas using knowledge base + LLM."""

    @property
    def name(self) -> str:
        return "explain_concept"

    @property
    def description(self) -> str:
        return "Giải thích thuật ngữ, khái niệm tài chính, công thức định lượng bằng tiếng Việt dễ hiểu."

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        entities = params.get("entities", {})
        retriever = context.get("retriever")
        llm_router = context.get("llm_router")
        question = entities.get("_question", "")

        # Search knowledge base
        knowledge_refs = []
        retrieved_docs = []
        if retriever:
            results = retriever.search(question, top_k=3)
            for r in results:
                doc = r.document
                entry = f"**{doc.title}**\n{doc.content}"
                if doc.metadata.get("formula"):
                    entry += f"\nCông thức: {doc.metadata['formula']}"
                if doc.metadata.get("example"):
                    entry += f"\nVí dụ: {doc.metadata['example']}"
                if doc.metadata.get("formula_python"):
                    entry += f"\nPython: `{doc.metadata['formula_python']}`"
                retrieved_docs.append(entry)
                knowledge_refs.append(f"{doc.category}/{doc.title}")

        kb_context = "\n\n".join(retrieved_docs)

        # Use LLM to create a comprehensive explanation
        if llm_router and kb_context:
            system = (
                "Bạn là giảng viên tài chính chuyên nghiệp. Giải thích khái niệm một cách dễ hiểu, "
                "có ví dụ thực tế từ thị trường Việt Nam. "
                "QUAN TRỌNG: Chỉ sử dụng thông tin từ tài liệu tham khảo được cung cấp. "
                "Nếu tài liệu không đủ thông tin, hãy nêu rõ là 'Theo tài liệu tham khảo...'. "
                "KHÔNG bịa đặt số liệu hoặc thông tin không có trong tài liệu. "
                "Giữ nguyên tất cả công thức, con số từ tài liệu tham khảo. "
                "Trả lời bằng tiếng Việt, ngắn gọn nhưng đầy đủ, có cấu trúc rõ ràng."
            )
            prompt = (
                f"Tài liệu tham khảo:\n{kb_context}\n\n"
                f"Câu hỏi: {question}\n\n"
                f"Hãy giải thích rõ ràng, dễ hiểu, dựa trên tài liệu tham khảo."
            )
            response = llm_router.generate_for_task(
                prompt, system, task_type="concept_explain", max_tokens=600
            )
            if response.text:
                return ToolResult(
                    success=True,
                    answer_text=response.text,
                    knowledge_refs=knowledge_refs,
                )

        # Fallback: return raw knowledge docs
        if kb_context:
            return ToolResult(
                success=True,
                answer_text=kb_context,
                knowledge_refs=knowledge_refs,
            )

        return ToolResult(
            success=False,
            error="Không tìm thấy thông tin về khái niệm này trong cơ sở kiến thức.",
        )
