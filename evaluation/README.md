# RAG evaluation and regression gates

`cases.jsonl` is a versioned, deliberately small smoke suite. Extend it with
reviewed production failures before changing retrieval, models, sources, or
prompts. Keep live-data cases separate from knowledge cases: a reference answer
for a live quote expires, while the assertion that the answer contains source
and retrieval time does not.

Run the CI-safe deterministic gate:

```bash
python -m evaluation.run_benchmark --engine core
```

It writes a timestamped input/output trace and checks routing accuracy,
non-empty answers, citation/reference coverage, and Retrieval Hit@5. It does
not claim semantic quality.

For judge-model evaluation, install the declared optional dependencies and set
the judge credentials required by the selected framework:

```bash
python -m evaluation.run_benchmark --engine ragas
python -m evaluation.run_benchmark --engine deepeval
```

RAGAS is configured for faithfulness, answer relevancy, context precision,
context recall, context relevance, noise sensitivity and response groundedness.
All require a configured judge model. Pin the RAGAS/LangChain combination in a
lock file before enabling the job in CI; unbounded LangChain major upgrades can
break RAGAS provider imports.

DeepEval evaluates answer relevancy, faithfulness, hallucination, contextual
precision, and contextual recall in the runner. The release suite must also
include `BiasMetric`, `ToxicityMetric`, and adversarial variants for robustness
(prompt injection in retrieved text, Vietnamese typo/accent variants, ticker
collisions, stale-date questions, and empty-context refusal). Set explicit
thresholds in CI only after collecting the first trusted baseline.

Promotion rule: no regression in retrieval Hit@5 or citation coverage; no
semantic metric may drop by more than the agreed tolerance; every live answer
must have a provider, observation/retrieval time, and no mock-data provenance.
