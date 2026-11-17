# agentkit

A small agent runtime written from scratch (no LangChain / LangGraph), about 750 lines.
It powers three apps: [holdout](https://github.com/cacheycat/holdout),
[casefile](https://github.com/cacheycat/casefile) and [undertow](https://github.com/cacheycat/undertow).

| Module | What it does |
|---|---|
| `graph.py` | Bounded `StateGraph`: nodes, conditional routes, a hard step limit |
| `runner.py` | Event-sourced runs in background threads, replayable over SSE |
| `memory.py` | Long-term lessons ranked by relevance x learned utility (Laplace-smoothed wins/losses) |
| `rag.py` | Hybrid BM25 + TF-IDF retrieval with reciprocal-rank fusion |
| `llm.py` | JSON-schema outputs, 2 retries, deterministic fallback per call site. Provider: Anthropic API, else headless `claude -p` with tools disabled, else none |
| `store.py` | SQLite run/event/memory store |
| `serve.py` | FastAPI scaffolding: run endpoints, SSE, static UI |
| `http.py` | `fetch_json` with a certifi-backed SSL context |
| `web/` | Shared `kit.js` / `kit.css` used by the three UIs |

## Install

```bash
pip install "agentkit @ git+https://github.com/cacheycat/agentkit.git"
# local development
pip install -e ".[dev]"
```

## Develop

```bash
pytest
ruff check .
```
