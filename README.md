# Zero-Leak RAG Lab — Identity-Aware Enterprise Grounding & RLS Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B%20Zero--Dependency-10b981.svg)](server.py)
[![Default LLM: Local Ollama](https://img.shields.io/badge/Default%20LLM-Local%20Ollama%20%28Onboard%29-22c55e.svg)](#llm-engine-modes-local-ollama-default--optional-cloud-apis)
[![Hybrid Search: BM25 + Vector RRF](https://img.shields.io/badge/Retrieval-BM25%20%2B%20Dense%20Vector%20%2B%20RRF-06b6d4.svg)](raglab/engine.py)
[![Security: Pre-Retrieval ACL & RLS](https://img.shields.io/badge/Security-Pre--Retrieval%20IAM%20%2B%20BigQuery%20RLS-f59e0b.svg)](raglab/engine.py)

**Zero-Leak RAG Lab** is a zero-dependency, local-first **Enterprise AI Grounding & Security Architecture Workbench** built to demonstrate—and stress-test—how production Retrieval-Augmented Generation (`RAG`) systems defeat the **"Confused Deputy"** data-leakage anti-pattern by enforcing **Pre-Retrieval Identity Propagation**, **BigQuery Row-Level Security (`RLS`)**, **Hybrid Search (`Sparse BM25 + Dense Semantic Vector + Reciprocal Rank Fusion`)**, and **Prompt-Injection & Citation Grounding Guardrails**.

---

## Why Naive Enterprise RAG Leaks Data ("Confused Deputy" Anti-Pattern)

Most prototype RAG pipelines index enterprise documents, data warehouses, and issue trackers using a single privileged backend service account, retrieve the global `Top-K` chunks, and rely on a system prompt (*"Do not share unauthorized data"*) to restrict output. That fails in two ways:
1. **Prompt-Window Data Leakage:** Unauthorized M&A filings, out-of-region financial rows, or HR/HIPAA records enter the LLM context window and leak via indirect summaries or prompt injection.
2. **Post-Filter `Top-K` Starvation:** Even if chunks are filtered *after* vector retrieval, restricted records crowd out the `Top-K` buffer, leaving legitimate callers with `0` results.

```
+----------------------------------------------------------------------------------------------------+
|                      ZERO-LEAK RAG LAB // IDENTITY-AWARE GROUNDING STUDIO (:8111)                  |
|                                                                                                    |
|  CALLER PERSONA (OAuth / OIDC Claims + Region Scope)                                               |
|    ├── Jordan (US-West AE)     ├── Marcus (Principal SRE)     ├── Priya (VP Finance)   ├── Elena   |
|    |                                                                                               |
|    +---> [1. Model Armor Input Screen] ---> Prompt-injection & privilege-escalation check          |
|    |                                                                                               |
|    +---> [2. Pre-Retrieval ACL & RLS Filter] (Enforced BEFORE scoring or ranking: Δ_unauth = ∅)    |
|    |       ├── Enterprise Doc Store (Group ACLs)                                                   |
|    |       ├── BigQuery Analytical Warehouse (Regional Row-Level Access Policies)                  |
|    |       └── Issue Tracker MCP Connector (Project & Role RBAC)                                   |
|    |                                                                                               |
|    +---> [3. Hybrid Retrieval + Reciprocal Rank Fusion (RRF)]                                      |
|    |       ├── Sparse BM25 Ranker (exact ticket IDs like SEC-401, SKUs, error codes)               |
|    |       └── Dense Semantic Vector Ranker (conceptual synonyms like M&A <-> acquisition)         |
|    |                                                                                               |
|    +---> [4. Grounded Synthesis + Citation Verifier] (Local Ollama default or Cloud LLM APIs)      |
|            └── Verifies every [DOC-*] / [BQ-ROW-*] / [SEC-*] citation against authorized context   |
+----------------------------------------------------------------------------------------------------+
```

---

## Four Interactive Workbench Modules (`http://127.0.0.1:8111`)

1. **Tab 1 — Side-by-Side Naive ("Confused Deputy") vs. Zero-Leak Identity-Propagated RAG:**
   - Runs both architectures concurrently in a `ThreadPoolExecutor` for any caller persona (`US-West Sales Rep`, `Principal SRE`, `VP Finance`, or `CEO — Least-Privilege HR Test`) and compares retrieved chunks, leaked chunk IDs (`DOC-MNA-004`, `BQ-ROW-103`, `DOC-HR-006`), `BM25` vs. `Dense` vs. `RRF` scores, prompt-injection telemetry, and verified `[ID]` citations.
2. **Tab 2 — `RAG vs. Long-Context (1M+) vs. Supervised Fine-Tuning` Trade-Off Calculator:**
   - Models corpus token volume (`250K` to `50M+` tokens), update frequency (`Real-Time` to `Monthly`), daily query load, citation requirements, and per-user ACL constraints to recommend the right grounding pattern with order-of-magnitude latency and cost estimates.
3. **Tab 3 — Code-Level Connector Security Bug Hunt:**
   - Four interactive Python/SQL security reviews (*Post-Filter `Top-K` Starvation*, *Pure Dense Vector Missing Exact Ticket IDs*, *Unscoped Semantic Cache Bleed*, and *Confused-Deputy Static Service Account Keys + SQL Injection*) with line-by-line production remediations.
4. **Tab 4 — Multi-Connector Corpus & ACL Matrix Inspector:**
   - Inspects all 12 indexed records across the **Enterprise Document Store**, **BigQuery RLS Warehouse**, and **Issue Tracker MCP Connector**, showing exact group ACLs and regional row predicates per persona.

---

## LLM Engine Modes: Local Ollama Default + Optional Cloud APIs

| Route | Provider(s) | Configuration |
| :--- | :--- | :--- |
| **1. Local Onboard Model *(Default)*** | **Ollama** (`http://127.0.0.1:11434`, e.g., `llama3.2:3b`) | Auto-detected via `/api/tags` — 100% local, private, zero API cost. Includes transparent offline fallback notice if no LLM endpoint is reachable. |
| **2. Cloud Frontier APIs *(Optional)*** | **Google Gemini** (`gemini-2.5-flash`), **OpenAI** (`gpt-4o-mini`), **Anthropic Claude** (`claude-3-7-sonnet-latest`) | Supply an API key in volatile session memory via the UI or set `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in a gitignored `.env` file. |

---

## Quickstart

Requires **only Python 3.10+ standard library** (zero `pip install` dependencies required):

```bash
# Start Zero-Leak RAG Lab on http://127.0.0.1:8111
./run.sh
```

### Run the Automated Unit & Security Test Suite

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
