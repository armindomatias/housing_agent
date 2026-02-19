# Observability: LangSmith + Structured Logging

## Goal

Add full observability to the 5-node LangGraph pipeline (scrape → classify → group → estimate → summarize):

1. **LangSmith** — automatic tracing of every LLM call with token counts, cost, and latency
2. **structlog** — structured JSON logging with request context (`request_id`, `property_url`) bound to every log line

## Scope

- [x] Centralized OpenAI client factory (`openai_client.py`) with optional LangSmith wrapping via `wrap_openai`
- [x] structlog configuration (`logging_config.py`) — JSON output in production, colored console in debug mode
- [x] Request context middleware (`middleware.py`) — generates `request_id` per request, adds `X-Request-ID` response header
- [x] Structured log calls in all services, routers, and graph nodes (no more f-string log messages)
- [x] `LANGCHAIN_TRACING_V2` disabled in tests via `conftest.py`
- [x] Unit tests for OpenAI client factory and logging config
- [x] Integration tests for `X-Request-ID` middleware header

## Decisions

| Decision | Rationale |
|----------|-----------|
| `wrap_openai` over `ChatOpenAI` | Zero response-format migration; works with existing `AsyncOpenAI` calls |
| `structlog` over `python-json-logger` | Context binding via `contextvars`, processor chain, first-class test support |
| LangSmith dashboard for cost/token data | No custom DB storage needed at this stage |
| FastAPI middleware for request context | Automatic for every route; no endpoint boilerplate |
| `PrintLoggerFactory` (not `stdlib.LoggerFactory`) | Simpler setup; `add_logger_name` processor removed since it requires stdlib logger |

## Files Changed

### New Files

| File | Description |
|------|-------------|
| `backend/app/services/openai_client.py` | Factory that returns `AsyncOpenAI`, wrapped by LangSmith when `LANGCHAIN_TRACING_V2=true` |
| `backend/app/logging_config.py` | `setup_logging(debug)` configures structlog with JSON or console renderer |
| `backend/app/middleware.py` | `RequestContextMiddleware` generates `request_id` and binds to structlog contextvars |
| `backend/tests/unit/test_openai_client.py` | Unit tests for client factory |
| `backend/tests/unit/test_logging_config.py` | Unit tests for logging config and context binding |
| `docs/features/observability/README.md` | This document |

### Modified Files

| File | Change |
|------|--------|
| `backend/pyproject.toml` | Added `langsmith>=0.2.0` and `structlog>=24.0.0` |
| `backend/app/config.py` | Added `langsmith_api_key`, `langsmith_project`, `langchain_tracing_v2` settings |
| `backend/.env.example` | Added LangSmith env var documentation |
| `backend/app/main.py` | Replaced `logging.basicConfig` with `setup_logging()`, added `RequestContextMiddleware` |
| `backend/app/services/image_classifier.py` | Use `get_openai_client()`, replace `logging` with `structlog` |
| `backend/app/services/renovation_estimator.py` | Use `get_openai_client()`, replace `logging` with `structlog` |
| `backend/app/api/v1/analyze.py` | Replace `logging` with `structlog`, bind `property_url` to context |
| `backend/app/graphs/main_graph.py` | Replace `logging` with `structlog` |
| `backend/tests/conftest.py` | Disable LangSmith tracing in tests, add structlog test configuration |
| `backend/tests/integration/test_api.py` | Add `X-Request-ID` middleware tests |

## How to Use

### Enable LangSmith Tracing

Add to `backend/.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGSMITH_API_KEY=lsv2_your_key_here
LANGSMITH_PROJECT=rehabify
```

Run a property analysis, then visit https://smith.langchain.com to see the full trace with:
- Each LangGraph node as a span
- Every GPT-4o and GPT-4o-mini call with token counts, cost, and latency
- Input/output for each LLM call

### Debug Logging (colored console)

```env
DEBUG=true
```

Output:
```
2024-01-15T10:23:45Z [info     ] api_startup    cors_origins=['http://localhost:3000']
2024-01-15T10:23:47Z [info     ] classification_strategy_chosen tagged_count=12 gpt_count=3 total=15
```

### Production Logging (JSON)

```env
DEBUG=false  # default
```

Output:
```json
{"event": "classification_strategy_chosen", "level": "info", "tagged_count": 12, "gpt_count": 3, "total": 15, "request_id": "550e8400-...", "property_url": "https://...", "timestamp": "2024-01-15T10:23:47Z"}
```

### Request ID Correlation

Every response includes `X-Request-ID`. Pass it when reporting issues:

```bash
curl -v http://localhost:8000/health
# < X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

## Log Level Reference

| Level | Used for |
|-------|---------|
| DEBUG | Raw LLM response content |
| INFO | Pipeline steps, classification strategy, service startup |
| WARNING | JSON parse retries, clustering fallbacks, null LLM responses |
| ERROR | Failed API calls, unrecoverable errors |
