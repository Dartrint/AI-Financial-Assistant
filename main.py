"""Command-line entry point for the three-layer Financial Assistant.

The CLI deliberately uses the same source aggregator and agent as FastAPI.
It never creates mock data: a failed live source results in an empty statement
dataset, while knowledge and live-quote questions remain independently usable.
"""

from __future__ import annotations

import argparse
import os

import pandas as pd

from agent import FinancialAgent
from market_data.aggregator import DataAggregator

SYMBOLS = ["VCB", "BID", "VNM"]
YEARS = list(range(2020, 2025))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Financial Assistant")
    parser.add_argument("--question", help="Câu hỏi cần trả lời")
    parser.add_argument("--interactive", action="store_true", help="Chạy chat tương tác")
    parser.add_argument("--symbols", nargs="*", default=SYMBOLS, help="Danh sách mã chứng khoán")
    parser.add_argument("--years", nargs="*", type=int, default=YEARS, help="Danh sách năm BCTC")
    return parser


def load_statement_dataset(aggregator: DataAggregator, symbols: list[str], years: list[int]) -> pd.DataFrame:
    """Step 1 — load only verified annual-statement data for offline analysis."""
    return aggregator.fetch_multiple(symbols, years, use_mock_fallback=False)


def print_result(result: dict) -> None:
    """Step 4 — render the answer and its source evidence in a CLI-safe form."""
    print(result["answer"])
    for citation in result.get("citations", []):
        source = citation.get("source", "unknown source")
        label = citation.get("ticker") or citation.get("indicator") or ""
        print(f"  Nguồn: {source} {label}".rstrip())


def main() -> None:
    args = build_parser().parse_args()
    if not (os.getenv("GROQ_API_KEY") or os.getenv("QROQ_API_KEY")):
        print("Không có Groq API key; hệ thống dùng parser/RAG deterministic khi có thể.")

    # Step 1: create data adapters and retrieve annual financial statements.
    aggregator = DataAggregator()
    dataset = load_statement_dataset(aggregator, args.symbols, args.years)
    print(f"Đã nạp {len(dataset)} dòng BCTC đã xác thực.")

    # Step 2: create the router. It decides RAG vs live data vs combined flow.
    agent = FinancialAgent(dataset=dataset, aggregator=aggregator)

    # Step 3: invoke the shared orchestration pipeline for one or many queries.
    if args.question:
        print_result(agent.answer(args.question))
        return

    if args.interactive:
        print("Nhập câu hỏi (Enter trống để dừng):")
        while question := input("Bạn: ").strip():
            print_result(agent.answer(question))
        return

    print("Dùng --question hoặc --interactive. Ví dụ: --question \"P/E của FPT hiện tại là bao nhiêu?\"")


if __name__ == "__main__":
    main()
