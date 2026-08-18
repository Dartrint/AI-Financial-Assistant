# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Inferred from the implemented dashboard and Vietnamese copy: investors and
financial analysts working in Vietnamese who need fast, source-aware answers
about listed companies, annual statements, market data, and macroeconomics.

## Product Purpose

AI Financial Assistant routes a question to live market data, verified annual
statements, or a knowledge retrieval path, then returns an answer with the
appropriate provenance. Success is a decision-useful answer without presenting
stale knowledge as a current market fact.

## Positioning

The product explicitly separates real-time market/tool data from educational
RAG knowledge and financial-statement calculations, rather than treating one
vector store as the source of every answer.

## Operating Context

Users ask a natural-language question, inspect an answer and its confidence or
source metadata, and may open a ticker detail view. The application exposes a
FastAPI dashboard plus `/ask`, overview, ticker, source-health, and architecture
APIs.

## Capabilities and Constraints

The existing application is FastAPI with a server-rendered HTML dashboard.
Financial claims must preserve available source/as-of information. Live data may
be unavailable; the interface must make loading, unavailable, and stale states
clear. These product facts are inferred from repository evidence pending user
confirmation.

## Evidence on Hand

`app.py`, `agent.py`, `templates/index.html`, the local DuckDB cache and Qdrant
data are the available product evidence. No approved logo, visual identity,
customer testimonials, or verified benchmark numbers are available.

## Product Principles

1. Surface provenance and freshness before confidence theatre.
2. Keep the user in one focused question-to-evidence workflow.
3. Make system status legible without overwhelming the analytical task.
4. Treat unavailable data as an honest state, not an empty decorative panel.

## Accessibility & Inclusion

Vietnamese language is primary. Keyboard submission, visible focus states,
semantic labels, contrast, and responsive layouts are required.
