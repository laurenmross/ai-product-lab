# Experiment 01 · AI product analyst

**Question:** can an AI agent answer real product-analysis questions about Lorem Work accurately? Which architecture choices actually make it better: retrieval, SQL tools, skills?

**Status:** not started. V0 (the question set) comes first.

## Versions

Each version is measured against the same question set, and each must beat the previous one to justify its added complexity.

| Version | Architecture | What it tests |
|---|---|---|
| **V0** | ~40 questions with known answers, plus a scoring script | Builds the eval first, so there's no version without a baseline |
| **V1** | Plain model call, no data access | How much the model makes up when it can't look anything up |
| **V2** | + retrieval over Lorem Work's help-center docs | Embeddings, chunking, and when RAG helps |
| **V3** | + SQL tool over usage data, also exposed as an MCP server | Tool calling, permissions, and the model deciding what to look up |
| **V4** | Docs + SQL + support tickets, with vs without an analysis skill | Combining evidence, and whether a skill measurably helps |

Question types (each version is scored on each type separately):
- **Lookup:** a number from the data ("What share of paid-social signups activated?")
- **Explain:** needs the docs ("Why might a member fail to connect Slack?")
- **Investigate:** needs both ("Why are value-unclear users stalling, and what would you test?")

Each version gets accuracy by question type, cost per question, latency, example failures, and a `LEARNINGS.md`.
