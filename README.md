# Apple Support Bot

A production-ready AI support bot for Apple devices and services.

Built with FastAPI + LangGraph + PageIndex + Ragas + Rival AI.

Companion article: *[I built a production-ready AI support bot. Here's every decision I made.]()*

---

## Architecture

```
POST /query
  │
  ├─ Middleware: JWT auth · rate limiting (slowapi) · input guard
  │
  ├─ Semantic cache check (GPTCache server)
  │     └─ HIT → return immediately
  │
  └─ LangGraph graph (LangSmith traces everything)
       ├─ safety_gate       Presidio PII scrub + Rival attack detection (parallel)
       ├─ query_intelligence  1 structured LLM call → intent, sub_queries, complexity
       ├─ session_memory    LangGraph PostgresSaver checkpointer
       ├─ context_retrieval PageIndex tree search + MongoDB
       ├─ execution         Gemini Flash / Pro / parallel sub-queries (Send API)
       ├─ output_validation Ragas faithfulness + custom completeness metric
       └─ cache_store       GPTCache write + structlog summary
```

## Stack

| Layer | Tool |
|---|---|
| API framework | FastAPI |
| Graph orchestration | LangGraph |
| Auth | python-jose |
| Rate limiting | slowapi |
| PII scrubbing | presidio-analyzer + presidio-anonymizer |
| Attack detection | rival-ai (Bhairava-0.4B, separate microservice) |
| Semantic caching | GPTCache (server mode) |
| RAG retrieval | PageIndex + MongoDB (motor) |
| Session memory | LangGraph PostgresSaver + asyncpg |
| LLM (low complexity) | Gemini 2.0 Flash (langchain-google-genai) |
| LLM (high complexity) | Gemini 2.5 Pro or GPT-4o (configurable) |
| Hallucination detection | Ragas Faithfulness |
| Completeness check | Custom LLM-as-judge metric |
| Observability (LLM) | LangSmith |
| Observability (app) | structlog |
| Retries | tenacity |
| Circuit breaking | pybreaker |
| HTTP client | httpx |

## Quickstart

**1. Clone and configure**

```bash
git clone https://github.com/your-handle/apple-support-bot
cd apple-support-bot
cp .env.example .env
# Fill in your API keys in .env
```

**2. Index your Apple support documents**

```bash
# Run once before starting the app
python -m prep.index_docs --pdf path/to/apple-support-guide.pdf --doc-id apple-support
```

**3. Start all services**

```bash
docker compose up --build
```

This starts:
- `app` — main FastAPI app on port 8000
- `rival-service` — Rival AI microservice on port 8002
- `gptcache` — GPTCache server on port 8001
- `mongodb` — document trees on port 27017
- `postgres` — session memory on port 5432

**4. Make a request**

```bash
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I factory reset my MacBook Pro?", "session_id": "session-abc"}'
```

## Project structure

```
apple-support-bot/
├── main.py                        # FastAPI app, /query endpoint
├── config.py                      # Settings via pydantic-settings
├── graph/
│   ├── state.py                   # SupportBotState TypedDict
│   ├── graph.py                   # StateGraph definition + compile
│   └── nodes/
│       ├── safety_gate.py         # Presidio + Rival (asyncio.gather)
│       ├── query_intelligence.py  # Structured LLM call
│       ├── session_memory.py      # History trimming
│       ├── context_retrieval.py   # PageIndex + MongoDB
│       ├── execution.py           # Model selection + Send fan-out
│       ├── output_validation.py   # Ragas + completeness
│       └── cache_store.py         # GPTCache write + final log
├── services/
│   └── rival_service/
│       ├── main.py                # Standalone FastAPI microservice
│       ├── requirements.txt
│       └── Dockerfile
├── metrics/
│   └── completeness.py            # LLM-as-judge completeness metric
├── prompts/
│   └── v1/
│       ├── query_intelligence.txt
│       ├── generation.txt
│       └── completeness_judge.txt
├── prep/
│   └── index_docs.py              # Offline: PageIndex → MongoDB
├── resilience/
│   ├── breakers.py                # pybreaker circuit breakers
│   └── retry.py                   # tenacity retry decorators
├── middleware/
│   ├── auth.py                    # JWT verification
│   ├── rate_limit.py              # slowapi limiter
│   └── input_guard.py             # Length + encoding check
├── observability/
│   └── logging.py                 # structlog setup
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `LOW_COMPLEXITY_MODEL` | `gemini-2.0-flash` | Model for simple queries |
| `HIGH_COMPLEXITY_MODEL` | `gemini-2.5-pro` | Model for complex queries. Set to `gpt-4o` to use OpenAI |
| `FAITHFULNESS_THRESHOLD` | `0.7` | Ragas score below this triggers a warning |
| `COMPLETENESS_THRESHOLD` | `0.6` | Completeness score below this triggers a warning |
| `MAX_INPUT_CHARS` | `4000` | Queries longer than this are rejected with 400 |
| `MAX_SESSION_TURNS` | `10` | How many conversation turns to keep in context |

## Prompt versioning

Prompts live in `prompts/v{n}/`. The active version is set in `graph/nodes/query_intelligence.py`. The version string is stored in LangGraph state and logged with every request, so you can correlate quality changes with prompt changes in LangSmith.

To make a new prompt version: copy `prompts/v1/` to `prompts/v2/`, edit, and update `PROMPT_VERSION` in the node.

## Circuit breakers and fallbacks

| Dependency | Breaker opens after | Fallback behaviour |
|---|---|---|
| Rival (attack detection) | 5 failures | Allow request through, log warning |
| PageIndex / MongoDB | 5 failures | Empty context, LLM answers from knowledge |
| GPTCache | 10 failures | Skip cache, continue normally |
| LLM provider | — (tenacity retries x3) | 503 to user |

## What's next

- **Eval regression suite** — LangSmith datasets + evaluations to catch regressions when prompts or models change
- **Streaming output** — FastAPI `StreamingResponse` with LangChain async streaming
- **A/B model testing** — route N% of traffic to a new model, compare scores before cutting over
- **Long-term cross-session memory** — user preference store (device model, past issues, communication style)
