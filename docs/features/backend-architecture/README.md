# Backend Architecture

This document explains the design decisions behind the Rehabify backend: how services are structured, why things are wired the way they are, and how the LangGraph pipeline works end-to-end.

---

## Table of Contents

1. [Service Lifecycle & Dependency Injection](#1-service-lifecycle--dependency-injection)
2. [LangGraph Pipeline](#2-langgraph-pipeline)
3. [Image Classification](#3-image-classification)
4. [Renovation Estimation](#4-renovation-estimation)
5. [Concurrency Model](#5-concurrency-model)
6. [Data Flow (end-to-end)](#6-data-flow-end-to-end)
7. [Testing Strategy](#7-testing-strategy)

---

## 1. Service Lifecycle & Dependency Injection

### The problem with naive service creation

The most natural-looking approach — instantiating a service inside a route handler or inside a LangGraph node — is expensive and incorrect:

```python
# BAD: creates a new AsyncOpenAI client (TCP connection pool) on every request
async def estimate_node(state):
    estimator = RenovationEstimatorService(openai_api_key=settings.openai_api_key)
    ...
```

A single analysis request runs five nodes, each of which would instantiate its own `AsyncOpenAI` client. That means 4–5 leaked HTTP connection pools per request and the overhead of re-establishing TLS sessions repeatedly.

### The solution: lifespan startup + `app.state`

FastAPI's `lifespan` context manager runs once at process startup and once at shutdown. We create every service there and store the instances on `app.state`:

```
main.py lifespan startup
│
├── IdealistaService(apify_token)          ← one httpx client
├── ImageClassifierService(api_key, model) ← one AsyncOpenAI client
├── RenovationEstimatorService(api_key, model) ← one AsyncOpenAI client
│
└── build_renovation_graph(services...)    ← one compiled LangGraph
        stored as app.state.graph
```

Request handlers retrieve the compiled graph from `app.state` and call it directly — no object creation at request time.

```python
# analyze.py — dependency injection via app.state
graph = request.app.state.graph
async for chunk in graph.astream({"url": url}):
    ...
```

**Shutdown** closes the `IdealistaService` httpx client cleanly so there are no dangling connections:

```python
yield  # serve requests

await idealista_service.close()  # graceful shutdown
```

### Why not FastAPI `Depends()`?

`Depends()` creates a new instance per request. For stateless utilities (database sessions, auth tokens) that is correct. For our services — which hold shared connection pools and compiled graphs — singleton-per-process is the right model.

---

## 2. LangGraph Pipeline

The analysis pipeline is a directed acyclic graph with five nodes:

```
scrape → classify → group → estimate → summarize → END
```

Each node is a pure async function with signature `(state: dict) -> dict`. Nodes never mutate state; they always return a new dict that merges additions over the previous state.

### Node overview

| Node | Step | What it does |
|------|------|-------------|
| `scrape_node` | 1/5 | Calls Apify to scrape the Idealista listing. Writes `property_data` and `image_urls` to state. |
| `classify_node` | 2/5 | Classifies every image into a room type. Reads Apify tags first (free), falls back to GPT-4o-mini. |
| `group_node` | 3/5 | Groups classifications by room. Filters out exterior/other images that don't need renovation estimates. |
| `estimate_node` | 4/5 | Analyzes each room concurrently with GPT-4o and produces cost ranges. |
| `summarize_node` | 5/5 | Calculates totals and generates a Portuguese-language narrative summary. |

### Error propagation

Every node checks `state.get("error")` before running. If an upstream node failed, the rest of the nodes pass through immediately. Errors are surfaced as `StreamEvent(type="error")` events so the frontend can display them.

### Dependency injection into nodes

LangGraph nodes must have the signature `(state) -> state`. To inject services without global variables, each node is a pure function that accepts services as keyword-only arguments:

```python
async def classify_node(state, *, classifier_service: ImageClassifierService):
    ...
```

`build_renovation_graph()` receives the pre-built services and creates thin closure wrappers:

```python
async def classify_with_services(state):
    return await classify_node(state, classifier_service=classifier_service)

graph.add_node("classify", classify_with_services)
```

This keeps the node functions independently testable (you can call `classify_node(state, classifier_service=mock)` directly in tests) while satisfying LangGraph's single-argument requirement.

### Streaming

Each node appends `StreamEvent` objects to `state["stream_events"]`. The API layer reads these events and pushes them to the frontend over Server-Sent Events. This gives the user real-time progress:

- Status events: "Fetching from Idealista...", "Classifying 24 photos..."
- Progress events: "Photo 3/24: bedroom detected", "Kitchen: fair condition, €5,000–€12,000"
- Result event: the complete `RenovationEstimate` as JSON

---

## 3. Image Classification

**File:** `backend/app/services/image_classifier.py`

### Two-phase classification

Classification uses a two-phase strategy ordered cheapest-first.

#### Phase 1 — Tag-based (free)

Apify's Idealista scraper attaches a "tag" string to each image (e.g. `"kitchen"`, `"bedroom"`). These are stored on `PropertyData.image_tags` as a `dict[url → tag]`.

`classify_from_tag(url, tag)` looks up the tag in `_APIFY_TAG_MAP` and returns an `ImageClassification` instantly with `confidence=0.9`. If the tag is missing or unrecognised, it returns `None` and the image falls through to Phase 2.

For a typical Portuguese listing, 60–80% of images are already tagged by Idealista, so Phase 2 handles only the remainder.

#### Phase 2 — GPT-4o-mini (paid)

Untagged images are sent to GPT-4o-mini with `detail="low"` (sufficient for room identification, cheaper than `"high"`). Calls are concurrent, bounded by a semaphore (default: 5 slots).

The model returns JSON:
```json
{"room_type": "cozinha", "room_number": 1, "confidence": 0.87}
```

`_map_room_type()` converts the string (English or Portuguese) to `RoomType`.

### Room number assignment

- **Tag-based:** always `room_number=1` — Apify tags carry no numbering information. Multiple bedroom images end up in the same `quarto_1` group, which is correct.
- **GPT-based:** GPT assigns a room number, allowing it to distinguish `bedroom_1` from `bedroom_2` when confidence is high enough.

### Grouping

`group_by_room()` produces a `dict[str, list[ImageClassification]]` keyed by `"{room_type_value}_{room_number}"` (e.g. `"cozinha_1"`, `"quarto_2"`). The estimator receives this dict — one key per room, one estimate per key.

### `get_room_label()`

Module-level helper (not a method) that converts `(RoomType, room_number)` to a human-readable Portuguese string:

```python
get_room_label(RoomType.BEDROOM, 2)   # → "Quarto 2"
get_room_label(RoomType.KITCHEN, 1)   # → "Cozinha"
get_room_label(RoomType.LIVING_ROOM, 1) # → "Sala"
```

Rooms that are unique (kitchen, living room, hallway) don't include the number.

---

## 4. Renovation Estimation

**File:** `backend/app/services/renovation_estimator.py`

### `analyze_room()`

The core method. Receives all image URLs for one room and calls GPT-4o with `detail="high"` (needed for condition assessment). Up to 4 images are sent per call to manage token cost.

The model returns JSON with:
- `condition`: excellent / bom / razoável / mau / necessita_remodelacao_total
- `condition_notes`: human-readable explanation
- `renovation_items`: list of `{item, cost_min, cost_max, priority, notes}`
- `cost_min`, `cost_max`: total room cost range in €
- `confidence`: model self-assessed confidence (0–1)

Confidence is boosted slightly for rooms with more images (more angles = more information). Cap is `1.0`.

### Fallback analysis

When GPT fails (API error, JSON parse error, timeout), `_get_fallback_analysis()` returns a conservative estimate from a hardcoded table:

| Room | Fallback range |
|------|---------------|
| Kitchen | €5,000–€15,000 |
| Bathroom | €3,000–€8,000 |
| Bedroom | €1,000–€3,000 |
| Living room | €1,500–€5,000 |
| Hallway | €500–€1,500 |

Fallback estimates have `confidence=0.3` so the frontend can signal uncertainty.

### `generate_summary()`

Calls GPT-4o with a text-only prompt (no images) to produce a concise Portuguese narrative summarising condition across all rooms and total cost. Fallback is a hardcoded template if the call fails.

### `create_estimate()`

Pure function — no API calls. Calculates totals, computes weighted-average confidence (weighted by `cost_max` so expensive rooms contribute more), and assembles the final `RenovationEstimate` model.

---

## 5. Concurrency Model

### Classification concurrency

`ImageClassifierService` holds an `asyncio.Semaphore(max_concurrent=5)`. Each `classify_single_image()` call acquires the semaphore before making the API request. This prevents hitting OpenAI's rate limits when a listing has 30+ images.

```
image_1 ─┐
image_2 ─┤─ semaphore (5 slots) ─→ GPT-4o-mini
image_3 ─┤
...       │
image_N ─┘
```

Tagged images bypass the semaphore entirely — they complete synchronously.

### Estimation concurrency

`RenovationEstimatorService.analyze_all_rooms()` submits all rooms as concurrent tasks and collects them with `asyncio.as_completed()`:

```python
tasks = [_bounded_analyze(room_type, room_number, urls) for ... in grouped_images]

for coro in asyncio.as_completed(tasks):
    analysis = await coro
    # fire progress event immediately
```

The semaphore (`max_concurrent=3`, lower than classification because GPT-4o calls are heavier) lives in `_bounded_analyze()`, not inside `analyze_room()`. This is a deliberate design choice:

- `analyze_room()` is a clean wrapper around one API call — easy to test in isolation
- `_bounded_analyze()` is an orchestration detail that belongs to `analyze_all_rooms()`
- Tests can `patch.object(estimator, "analyze_room", ...)` without accidentally bypassing concurrency control

**Wall-clock time comparison for a 5-room property:**

| Approach | Time |
|----------|------|
| Serial (one room at a time) | ~35 s |
| Parallel with semaphore=3 | ~12 s |

---

## 6. Data Flow (end-to-end)

```
POST /api/v1/analyze  { "url": "https://www.idealista.pt/imovel/..." }
│
│   SSE stream starts
│
├── scrape_node
│   ├── Apify actor fetches listing data
│   └── Returns: PropertyData { title, price, area_m2, image_urls[], image_tags{} }
│
├── classify_node
│   ├── Phase 1: tag-based classification (free, instant)
│   │     image_tags["url1"] = "kitchen"  →  RoomType.KITCHEN, confidence=0.9
│   └── Phase 2: GPT-4o-mini for untagged images (concurrent, rate-limited)
│         Response: {"room_type": "quarto", "room_number": 1, "confidence": 0.85}
│
├── group_node
│   ├── Groups by (room_type, room_number)
│   │     "cozinha_1": [img1, img3]
│   │     "quarto_1":  [img2, img5, img7]
│   └── Filters out exterior/other
│
├── estimate_node
│   ├── Submits one GPT-4o task per room (concurrent, semaphore=3)
│   └── Each room returns: { condition, renovation_items[], cost_min, cost_max }
│
└── summarize_node
    ├── Sums costs across rooms
    ├── GPT-4o generates Portuguese narrative
    └── Returns: RenovationEstimate { room_analyses[], total_cost_min, total_cost_max, summary }
```

### State shape

LangGraph state is a plain `dict`. Keys accumulate as the pipeline progresses:

```python
{
  # set by caller
  "url": str,
  "user_id": str | None,

  # set by scrape_node
  "property_data": PropertyData,
  "image_urls": list[str],

  # set by classify_node
  "classifications": list[ImageClassification],

  # set by group_node
  "grouped_images": dict[str, list[dict]],  # serialised for LangGraph

  # set by estimate_node
  "room_analyses": list[RoomAnalysis],

  # set by summarize_node
  "estimate": RenovationEstimate,
  "summary": str,

  # updated by every node
  "stream_events": list[StreamEvent],
  "current_step": str,
  "error": str | None,
}
```

Note: `grouped_images` is stored as `list[dict]` (not `list[ImageClassification]`) because LangGraph serialises state between nodes. `estimate_node` reconstructs the `ImageClassification` objects from those dicts.

---

## 7. Testing Strategy

### Unit tests

Services are tested in complete isolation. No real API calls are made.

**ImageClassifierService** (`tests/unit/test_image_classifier.py`):
- `_map_room_type()` — all Portuguese and English room strings
- `group_by_room()` — same type/number → grouped, different → separated
- `get_room_label()` — all RoomType values produce non-empty strings
- `classify_from_tag()` — known tags map correctly, unknown returns `None`
- `classify_images()` — tagged images skip GPT, untagged go to GPT, progress callback fires for all

**RenovationEstimatorService** (integration tests via `tests/integration/`):
- The service is currently tested through the API layer

### Integration tests

`tests/integration/test_api.py` tests the FastAPI layer using `TestClient`:
- `GET /` returns API info
- `GET /health` returns `{"status": "healthy"}`
- `GET /api/v1/analyze/health` returns healthy

### What is not tested (intentionally)

- Real OpenAI API calls — prohibitively expensive in CI, and unit tests mock the client
- Real Apify calls — same reason; integration tests use mock data
- LangGraph node wiring — the graph topology is simple enough that end-to-end manual testing catches issues

### Adding tests for a service

Follow the existing pattern in `test_image_classifier.py`:

1. Create a `mock_provider` or mock client fixture
2. Use `patch.object(service, "method_name", AsyncMock(return_value=...))` to mock outbound calls
3. Assert on the return value, not on internal state

---

## Files changed by the architecture refactor

| File | Change |
|------|--------|
| `app/main.py` | Services created once in lifespan; stored on `app.state` |
| `app/api/v1/analyze.py` | Graph retrieved from `app.state.graph` instead of built per request |
| `app/graphs/main_graph.py` | `build_renovation_graph()` accepts pre-built services; nodes use closure injection |
| `app/services/image_classifier.py` | `get_room_label()` moved to module level; tag-based classification added |
| `app/services/renovation_estimator.py` | Removed embedded `ImageClassifierService`; uses `get_room_label()` directly; `analyze_all_rooms()` is now concurrent |
| `tests/unit/test_image_classifier.py` | Updated to test standalone `get_room_label()` and tag-based classification |
