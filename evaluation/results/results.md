# AI Financial Assistant - Evaluation Results

## Summary

| Engine | Routing Accuracy | Answer Non-Empty Rate | Citation Coverage | Retrieval Hit@5 |
|--------|------------------|----------------------|-------------------|-----------------|
| Core | 0.90 | 1.00 | 0.70 | 1.00 |
| RAGAS | 0.90 | 1.00 | 0.70 | 1.00 |
| DeepEval | 0.90 | 1.00 | 0.70 | 1.00 |

## Core Metrics (All Engines)

- **Routing Accuracy**: 90% - Intent classification correctly routes 9/10 queries
- **Answer Non-Empty Rate**: 100% - All queries produce non-empty responses
- **Citation/Reference Coverage**: 70% - 7/10 responses include knowledge references
- **Retrieval Hit@5**: 100% - All relevant documents retrieved in top-5

## Test Cases (10 Total)

| Case ID | Category | Intent | Status |
|---------|----------|--------|--------|
| concept_roe | Financial Concept | concept_explain | ✅ Pass |
| concept_capm | Quant Finance | concept_explain | ✅ Pass |
| concept_wacc | Quant Finance | concept_explain | ✅ Pass |
| concept_cpi | Economics | concept_explain | ✅ Pass |
| macro_definition | Economics | concept_explain | ✅ Pass |
| live_pe | Market Data | market_data | ✅ Pass |
| live_cpi | Market Data | market_data | ⚠️ No Data Source |
| market_interpret | Market + Knowledge | market_and_knowledge | ✅ Pass |
| statement_metric | Financial Statement | metric_lookup | ⚠️ No Data |
| portfolio | Portfolio Theory | concept_explain | ⚠️ Wrong Tool |

## Detailed Results by Engine

### Core Engine
- All core metrics computed successfully
- No external dependencies required

### RAGAS Engine
- Core metrics: Same as core engine
- RAGAS evaluation: **Setup Error** - Missing `langchain_community.chat_models.vertexai` module
- To fix: Install RAGAS dependencies or configure Vertex AI

### DeepEval Engine
- Core metrics: Same as core engine
- DeepEval evaluation: **Skipped** - Missing `deepeval` module
- To fix: `pip install deepeval`

## Observations

### Strengths
1. **Excellent routing** - 90% accuracy on intent classification
2. **Perfect retrieval** - 100% hit rate for relevant documents
3. **Complete responses** - 100% non-empty answer rate
4. **Live market data** - Successfully fetches real-time P/E ratios (FPT: 12.38x)

### Areas for Improvement
1. **Citation coverage** - Only 70% of responses include knowledge references
2. **Missing data sources** - EcoData API not configured for CPI data
3. **Financial statement data** - No VCB 2024 revenue data available
4. **Tool selection** - Portfolio question incorrectly routed to market_data instead of explain_concept

## Recommendations

1. **Install RAGAS**: `pip install ragas` + configure LLM for evaluation
2. **Install DeepEval**: `pip install deepeval` for advanced metrics
3. **Configure EcoData API** for real-time macroeconomic data
4. **Add financial statement data source** for metric_lookup queries
5. **Improve tool routing** for portfolio/concept questions

## Files Generated

- `benchmark_core.json` - Core metrics only
- `benchmark_ragas.json` - Core + RAGAS (setup error)
- `benchmark_deepeval.json` - Core + DeepEval (skipped)

---
*Generated: 2026-08-18T14:35:03+00:00*