"""
tools/economic_analysis.py
Economic analysis tool — macro analysis, sector comparison, market context.
"""

from __future__ import annotations

import logging
from typing import Any

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class EconomicAnalysisTool(Tool):
    """Macro economic analysis and sector-level insights."""

    @property
    def name(self) -> str:
        return "economic_analysis"

    @property
    def description(self) -> str:
        return "Phân tích kinh tế vĩ mô: GDP, lạm phát, lãi suất, tỷ giá, tương quan ngành, market context Việt Nam."

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        entities = params.get("entities", {})
        retriever = context.get("retriever")
        llm_router = context.get("llm_router")
        question = entities.get("_question", "")

        # Search knowledge base for relevant economic context
        knowledge_refs = []
        kb_context = ""
        if retriever:
            results = retriever.search(question, top_k=5)
            for r in results:
                kb_context += f"\n- {r.document.title}: {r.document.content}"
                knowledge_refs.append(f"{r.document.category}/{r.document.title}")

        # Use LLM to synthesize answer
        if llm_router and kb_context:
            system = (
                "Bạn là chuyên gia phân tích kinh tế vĩ mô Việt Nam. "
                "Dựa trên kiến thức được cung cấp, trả lời câu hỏi ngắn gọn, chính xác. "
                "QUAN TRỌNG: Chỉ sử dụng thông tin từ tài liệu tham khảo. "
                "Nếu không có thông tin đủ, hãy nêu rõ nguồn và giới hạn. "
                "KHÔNG bịa đặt số liệu hoặc sự kiện không có trong tài liệu. "
                "Trả lời bằng tiếng Việt, có cấu trúc rõ ràng."
            )
            prompt = f"Kiến thức tham khảo:\n{kb_context}\n\nCâu hỏi: {question}\n\nTrả lời chính xác, ngắn gọn, có trích dẫn nguồn nếu có thể."
            response = llm_router.generate_for_task(
                prompt, system, task_type="concept_explain", max_tokens=500
            )
            if response.text:
                return ToolResult(
                    success=True,
                    answer_text=response.text,
                    knowledge_refs=knowledge_refs,
                )

        # Fallback: return raw knowledge
        if kb_context:
            return ToolResult(
                success=True,
                answer_text=f"**Thông tin kinh tế liên quan**:{kb_context}",
                knowledge_refs=knowledge_refs,
            )

        return ToolResult(
            success=False,
            error="Không tìm thấy thông tin kinh tế phù hợp cho câu hỏi này.",
        )
