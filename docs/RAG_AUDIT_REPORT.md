# Audit RAG — AI Financial Assistant

Audit date: 2026-08-18. This report separates evidence observed in the
repository from recommendations. No benchmark score is invented: the local
environment currently lacks `qdrant-client`, `ragas`, `vnstock`, and `vnai`, so
the semantic baseline cannot be validly measured here.

## Current architecture

```text
question → regex/optional LLM entity extraction → intent router
  ├─ current quote/macro → DataAggregator (vnstock / Yahoo / EcoData) → tool
  ├─ annual statement → vnstock cache / DuckDB → calculation tool
  └─ concept or interpretation → HybridRetriever → LLM answer

web/seed content → extract → clean → 800-character chunks → BGE embedding → Qdrant
seed JSON              └───────────────────────────────────────────────┘
                                      in-memory BM25 + dense + reranker
```

The intended separation between live values and RAG is sound. However, it is
not yet a single production retrieval plane: `HybridRetriever.build_index()`
loads only JSON seed documents in memory, while web ETL writes chunks to
Qdrant. As a result, the normal answer path does not retrieve those web chunks.

## Findings requiring action

| Priority | Evidence | Impact | Required resolution |
| --- | --- | --- | --- |
| P0 | Web chunks in Qdrant are absent from `HybridRetriever`'s memory corpus. | Newly ingested knowledge is effectively invisible to answers. | Move sparse+dense retrieval to Qdrant (native hybrid sparse vectors) or maintain one materialized corpus/index used by both paths. Add an ingestion-to-answer integration test. |
| P0 | `DataAggregator.fetch(... use_mock_fallback=True)` could create `MOCK_DATA` for callers that opt in. | Fabricated financial statements can reach answers/DuckDB. | Default is now `False`; retain source, `as_of`, `is_mock`, and block mock rows from persistence and response generation. |
| P0 | Current collection schema is fixed to a vector dimension inferred from `BGE_MODEL`. | Changing embedding model can silently make existing Qdrant collections incompatible. | Version collection names by embedding model/dimension; dual-write, benchmark, then alias cutover. |
| P1 | Default `BAAI/bge-small-en-v1.5` and MS-MARCO reranker are English-centric. | Weak Vietnamese finance retrieval/reranking. | Benchmark multilingual candidates: `BAAI/bge-m3` or `intfloat/multilingual-e5-large-instruct`; `BAAI/bge-reranker-v2-m3` or `jinaai/jina-reranker-v2-base-multilingual`. |
| P1 | Character chunking (800/150) cuts tables, filings and Vietnamese clauses; metadata lacks document version, language, issuer/ticker, filing period, as-of, license, and provenance hash. | Poor grounding, duplicates, stale citations and weak filtering. | Use document-aware chunks (heading/table/section), token length 350–550 with 50–80 overlap, parent documents, stable document/chunk/version IDs and rich metadata. |
| P1 | Query expansion previously fused raw incomparable scores and used string IDs as list indices. | Wrong documents may be returned. | Fixed in `retrieval/hybrid_retriever.py`: rank fusion over variants, identity-preserving position map, rerank candidates. |
| P1 | Source timestamps are ingestion time, not necessarily publisher update time; no revalidation/robots/license policy. | Freshness cannot be proven. | Capture HTTP ETag/Last-Modified, publisher date, content hash, license, crawl status and expiry. |
| P2 | Regex-first intent/entity routing is brittle for ticker collisions, mixed questions and Vietnamese accent/typo variants. | Wrong tool or answer boundary. | Add compact structured router with deterministic validation and a route test set. |
| P2 | Generated RAG answers receive reference labels but no per-claim URL citations. | Hallucination cannot be audited by users. | Require `[S1]` claim citations, source URL/published-at/retrieved-at, and abstention when evidence is insufficient. |

## Data inventory and assessment

| Existing source | Purpose | Assessment at audit date |
| --- | --- | --- |
| Seed JSON (financial/economics/quant/Vietnam market) | Definitions and examples | Small, manually written, mixed historical claims; no per-claim source/version. Some macro values cite 2023–2024 in prose and are stale for current-value questions. Keep only as educational corpus with `valid_to`/citation fields. |
| Investopedia, CFI, SEC, IMF factsheets, QuantConnect | Web ETL glossary | Suitable as supplementary education, not authoritative Vietnam market facts. Current configuration contains selected landing pages, no sitemap configured, no license/robots audit or revision capture. |
| Vietstock | Vietnam market web ETL | Useful secondary coverage, but one generic landing URL is not a reliable structured filing/news feed; requires permission and provenance checks. |
| vnstock | Vietnamese filings/market adapter | Intended primary adapter, but not installed in this environment. Cache contains 2022–2025 files; as of 2026-08-18 they cannot establish current coverage. |
| Yahoo Finance | Secondary quote/valuation | Useful fallback, but Vietnam symbol mapping, exchange timestamp, corporate actions and delayed quote semantics must be validated per field. |
| EcoData | Macro/quote adapter | Disabled by config and endpoints explicitly unverified; it is not a current source until contract/API schema and SLA are validated. |
| DuckDB | Verified annual-statement store | Good boundary concept, but source revisions, filing version/audit status and mock-data exclusion need enforcement. |

Recommended authoritative additions: NSO/GSO for official Vietnamese statistics and release calendar; it publishes national accounts, CPI and other statistical series ([NSO statistical data](https://www.nso.gov.vn/en/statistical-data/)). SBV for policy rates, central exchange rates and monetary releases; Ministry of Finance, HOSE/HNX/UPCoM disclosure feeds and issuer IR pages for original filings; IMF SDMX API for cross-country and vintage macro data ([IMF API](https://data.imf.org/en/Resource-Pages/IMF-API)) and WEO vintages ([IMF WEO](https://data.imf.org/en/datasets/IMF.RES%3AWEO?indicator_id=TX_RPCH)); World Bank and FRED for internationally comparable series. The IMF notes Vietnam's official NSDP connects GSO, SBV and Ministry of Finance publishers ([IMF e-GDDS notice](https://www.imf.org/en/news/articles/2019/07/17/pr19269-vietnam-implements-imfs-enhanced-general-data-dissemination-system)).

Do not scrape/paywall-bypass research reports. Ingest reports only when the
license permits internal indexing, retaining the original file and access rule.

## Target production design

Use a **hybrid Qdrant + LangGraph** architecture. LangGraph is the orchestration
layer, not the retrieval engine: nodes are `route → retrieve/execute-live →
verify → synthesize-cited → evaluate/log`. Keep current tools behind typed
interfaces. Use Qdrant for dense vectors plus sparse BM25/SPLADE (or an
OpenSearch companion) and metadata filters. Retrieve 30–50, RRF, rerank 10–20,
then compress to 4–8 cited passages. Parent-child retrieval should return a
small child chunk for ranking and its parent section/table for answering.

Graph RAG is not a first milestone. Add it only for entity-heavy questions
(issuer–subsidiary–sector–event–period relationships) after a canonical entity
registry and high-quality filings exist. LlamaIndex/Haystack can accelerate
document parsing/retrieval experiments; do not run competing orchestration
frameworks in production. DSPy is appropriate for offline prompt optimization
after the evaluation set is mature.

Required metadata:

```text
document_id, document_version, chunk_id, parent_id, source_url, source_type,
publisher, license, language, country, ticker, exchange, sector, report_type,
period_start/end, published_at, retrieved_at, valid_from/to, as_of,
content_hash, parser_version, embedding_model, is_primary_source
```

## Incremental updates and operations

`etl/state.py` and `etl/run_etl.py` now implement content-hash manifests: an
unchanged URL is not rechunked/re-embedded, and the manifest advances only after
successful upsert. This is a first step, not full synchronization: deletion of
obsolete chunks, HTTP ETag/Last-Modified, source-specific cursoring, retries,
dead-letter queue and observability still need implementation.

Schedule: quotes/trading calendar every 5–15 minutes only during exchange
hours; macro release checks hourly with an official-calendar trigger; disclosure
polling hourly; issuer filings/news daily; full source revalidation weekly; full
embedding refresh only on a model migration. Each job needs idempotency key,
watermark, retry budget, alert and data-quality checks (schema, row count,
freshness, duplicate/hash, anomalous numeric scale).

## Evaluation and benchmark protocol

The checked-in suite and runner are in `evaluation/`. It gives a reproducible
core gate and optional RAGAS/DeepEval judge runs. The first measured baseline
must record model, prompt, corpus snapshot, source timestamps, top-k, latency,
cost, judge model and seed. Do not compare runs with different corpus snapshots
without labelling the change.

Runtime audit after dependency installation: Qdrant, RAGAS and vnstock are now
present, but RAGAS 0.4.3 fails to import against the installed
`langchain-community` 0.4.2 because its VertexAI module was removed. Do not run
semantic CI on this unpinned environment; create a project virtual environment
and lock a compatible RAGAS/LangChain set first. `vnai` is installed but its
skill catalog requires a Vnstock API key; no key was read or changed during this
audit.

| Experiment | Fixed controls | Variable | Required metrics |
| --- | --- | --- | --- |
| Baseline | corpus snapshot, 50+ reviewed questions | current system | routing, Hit@k/MRR/nDCG, citations, latency/cost; RAGAS/DeepEval metrics |
| Retrieval | same model/corpus | dense vs BM25 vs hybrid, top-k, filters, query expansion | context precision/recall, noise sensitivity, nDCG, p95 latency |
| Embedding | same chunks/retrieval | multilingual embedding | recall@k, MRR, language slices |
| Reranker | same candidates | reranker on/off/model | precision@k, faithfulness, latency/cost |
| Data expansion | same code/model | primary-source corpus additions | date/issuer coverage, retrieval recall, groundedness |

Dashboard: publish the JSON traces to a small internal dashboard (or PostHog/
Grafana) with run ID, corpus/model versions, metric trend, cost/latency, failure
slices and links to question/context/answer. Never display a number as a
before/after result until both runs were executed on the same frozen test set.

## Prioritized roadmap

| Horizon | Change | Impact | Cost / complexity | ROI |
| --- | --- | --- | --- | --- |
| 1–3 days | Disable production mock fallback; fix multi-query; version source/as-of/citations; run 50-question baseline | Very high | Low | Very high |
| 1–3 days | Install missing runtime deps, pin environments, add CI core gate and review dataset | High | Low | Very high |
| 1–2 weeks | Unify Qdrant retrieval, multilingual embed/reranker A/B, metadata/filtering, parent-child chunks | Very high | Medium | High |
| 1–2 weeks | Official NSO/SBV/exchange/issuer ingestion with manifest, release calendars, observability | Very high | Medium | High |
| 1–3 months | Managed Qdrant/OpenSearch HA, LangGraph verification state machine, model/corpus registry, dashboard and SLOs | High | High | Medium–high |
| 1–3 months | Entity graph for filings/events only if benchmark shows multi-hop recall gap | Medium | High | Conditional |
