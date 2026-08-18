"""Run deterministic gates first, then optional RAGAS or DeepEval judges.

Usage:
  python -m evaluation.run_benchmark --engine core
  python -m evaluation.run_benchmark --engine ragas
  python -m evaluation.run_benchmark --engine deepeval

The core gate never calls a judge model.  It is the CI-safe regression gate;
RAGAS and DeepEval add semantic evaluation only when their judge credentials
and packages are configured.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import FinancialAgent

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "cases.jsonl"
DEFAULT_OUTPUT = ROOT / "results"


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _contexts(agent: FinancialAgent, question: str) -> list[str]:
    try:
        results = agent.retriever.search(question, top_k=5)
        return [f"{item.document.title}\n{item.document.content}" for item in results]
    except Exception:
        return []


def collect_records(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agent = FinancialAgent()
    records = []
    for case in cases:
        result = agent.answer(case["question"])
        contexts = _contexts(agent, case["question"]) if case["expected_titles"] else []
        records.append({
            "case": case,
            "question": case["question"],
            "answer": result.get("answer", ""),
            "contexts": contexts,
            "citations": result.get("citations", []),
            "knowledge_refs": result.get("knowledge_refs", []),
            "intent": result.get("intent"),
            "tool_used": result.get("tool_used"),
        })
    return records


def core_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    total = len(records) or 1
    routed = sum(r["intent"] == r["case"]["expected_intent"] for r in records)
    answered = sum(bool(r["answer"].strip()) for r in records)
    cited = sum(bool(r["citations"] or r["knowledge_refs"]) for r in records)
    retrieval_cases = [r for r in records if r["case"]["expected_titles"]]
    hits = 0
    for record in retrieval_cases:
        corpus = " ".join(record["contexts"]).lower()
        if any(title.lower() in corpus for title in record["case"]["expected_titles"]):
            hits += 1
    return {
        "routing_accuracy": routed / total,
        "answer_nonempty_rate": answered / total,
        "citation_or_reference_coverage": cited / total,
        "retrieval_hit_at_5": hits / (len(retrieval_cases) or 1),
    }


def run_ragas(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the RAGAS metric set lazily, preserving raw inputs on failure."""
    try:
        from datasets import Dataset
        from ragas import evaluate

        # RAGAS >=0.4 collections API.  Pin the working LangChain/RAGAS
        # combination in a lock file before production use.
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            ContextRelevance,
            Faithfulness,
            NoiseSensitivity,
            ResponseGroundedness,
        )
    except Exception as exc:
        return {"status": "setup_error", "reason": f"RAGAS import/configuration error: {type(exc).__name__}: {exc}"}

    rows = [
        {
            "question": r["question"], "answer": r["answer"],
            "contexts": r["contexts"], "ground_truth": r["case"]["reference_answer"],
        }
        for r in records if r["contexts"]
    ]
    if not rows:
        return {"status": "skipped", "reason": "No RAG contexts collected"}
    try:
        metrics = [
            Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall(),
            ContextRelevance(), NoiseSensitivity(), ResponseGroundedness(),
        ]
        result = evaluate(Dataset.from_list(rows), metrics=metrics)
        return {"status": "ok", "metrics": result.to_pandas().mean(numeric_only=True).to_dict()}
    except Exception as exc:  # Judge configuration is intentionally not hidden.
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def run_deepeval(records: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from deepeval import evaluate
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            ContextualRecallMetric,
            FaithfulnessMetric,
            HallucinationMetric,
        )
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        return {"status": "skipped", "reason": f"Missing dependency: {exc}"}
    cases = [
        LLMTestCase(input=r["question"], actual_output=r["answer"], retrieval_context=r["contexts"], expected_output=r["case"]["reference_answer"])
        for r in records if r["contexts"]
    ]
    if not cases:
        return {"status": "skipped", "reason": "No RAG contexts collected"}
    try:
        evaluate(cases, [AnswerRelevancyMetric(), FaithfulnessMetric(), HallucinationMetric(), ContextualPrecisionMetric(), ContextualRecallMetric()])
        return {"status": "ok", "note": "DeepEval emitted its detailed report to the configured reporter."}
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("core", "ragas", "deepeval"), default="core")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = collect_records(load_cases(args.cases))
    report: dict[str, Any] = {"created_at": datetime.now(timezone.utc).isoformat(), "engine": args.engine, "core": core_metrics(records), "records": records}
    if args.engine == "ragas":
        report["ragas"] = run_ragas(records)
    elif args.engine == "deepeval":
        report["deepeval"] = run_deepeval(records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"benchmark_{args.engine}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False, indent=2))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
