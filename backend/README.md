# Rehabify Backend

Python API that analyzes Portuguese property listings from Idealista and estimates renovation costs using AI photo analysis.

Give it an Idealista URL, it scrapes the listing, classifies every photo by room, then uses GPT-4 Vision to estimate what each room needs and how much it'll cost.

## How It Works

The backend runs a 5-step **LangGraph pipeline** that streams progress to the frontend via SSE:

```
[Idealista URL]
       |
   1. SCRAPE ──── Apify actor fetches listing data + photos
       |
   2. CLASSIFY ── GPT-4o-mini classifies each photo (kitchen, bedroom, bathroom...)
       |
   3. GROUP ───── Groups photos by room (3 kitchen photos = 1 kitchen, not 3)
       |
   4. ESTIMATE ── GPT-4o analyzes each room's condition + estimates renovation costs
       |
   5. SUMMARIZE ─ GPT-4o generates final report with totals
       |
[RenovationEstimate JSON streamed via SSE]
```

Each step emits `StreamEvent`s so the frontend can show real-time progress ("Classifying photo 3/18: Kitchen detected...").

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI entry point, CORS, lifespan
│   ├── config.py                # Settings from .env (pydantic-settings)
│   ├── api/v1/
│   │   └── analyze.py           # POST /analyze (SSE) + POST /analyze/sync
│   ├── models/
│   │   └── property.py          # All Pydantic models (PropertyData, RoomAnalysis, etc.)
│   ├── services/
│   │   ├── idealista.py         # Scrapes Idealista via Apify standby mode
│   │   ├── image_classifier.py  # Classifies photos with GPT-4o-mini
│   │   └── renovation_estimator.py  # Estimates costs with GPT-4o Vision
│   ├── graphs/
│   │   ├── main_graph.py        # LangGraph definition (5 nodes, linear flow)
│   │   └── state.py             # Graph state schema
│   ├── prompts/
│   │   └── renovation.py        # All AI prompts (in Portuguese)
│   └── agents/                  # Future agent definitions (empty)
├── tests/
│   ├── conftest.py              # Shared fixtures, env setup
│   ├── unit/
│   │   ├── test_models.py       # Pydantic model validation
│   │   ├── test_idealista.py    # URL validation, NDJSON parsing, result mapping
│   │   └── test_image_classifier.py  # Room type mapping, grouping
│   ├── integration/
│   │   └── test_api.py          # Endpoint tests (root, health)
│   └── regression/              # Bug-fix regression tests (empty)
├── pyproject.toml               # Dependencies + ruff/pytest config
└── .env.example                 # Environment variable template
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | API info (name, version, docs link) |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/analyze` | Analyze property with **SSE streaming** |
| `POST` | `/api/v1/analyze/sync` | Analyze property without streaming |
| `GET` | `/api/v1/analyze/health` | Analyzer service health check |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |

### `POST /api/v1/analyze` (Streaming)

Request:
```json
{
  "url": "https://www.idealista.pt/imovel/12345678/",
  "user_id": ""
}
```

Response: SSE stream of `StreamEvent` objects:
```
data: {"type": "status", "message": "A obter dados do Idealista...", "step": 1, "total_steps": 5}
data: {"type": "progress", "message": "A classificar foto 1/18: Cozinha detectada", "step": 2, ...}
...
data: {"type": "result", "message": "Estimativa completa: 15,000€ - 35,000€", "step": 5, "data": {"estimate": {...}}}
```

### `POST /api/v1/analyze/sync`

Same request, returns a single JSON response:
```json
{
  "success": true,
  "estimate": {
    "property_url": "...",
    "property_data": { "title": "...", "price": 185000, ... },
    "room_analyses": [
      {
        "room_label": "Cozinha",
        "condition": "mau",
        "cost_min": 5000,
        "cost_max": 12000,
        "renovation_items": [...]
      }
    ],
    "total_cost_min": 15000,
    "total_cost_max": 35000,
    "summary": "O imóvel necessita de remodelação..."
  }
}
```

## Data Models

All defined in `app/models/property.py`:

- **`PropertyData`** — Scraped listing data (price, area, rooms, photos, coordinates, image tags, etc.)
- **`ImageClassification`** — Result of classifying one photo (room type + confidence)
- **`RoomAnalysis`** — Condition assessment + itemized renovation costs for one room
- **`RenovationItem`** — Single renovation task (e.g., "Kitchen cabinets: 3,000-6,000€")
- **`RenovationEstimate`** — Final output with all room analyses, totals, and summary
- **`StreamEvent`** — SSE event sent during processing (status, progress, error, result)

## Services

### `IdealistaService` (`services/idealista.py`)

Scrapes property data from Idealista using the `dz_omar/idealista-scraper-api` Apify actor in **standby mode** — a single POST that returns NDJSON directly, no polling.

- Validates URLs (must be `idealista.pt/imovel/<id>`)
- Retry logic with exponential backoff (2s, 4s, 8s) for transient 5xx/timeout errors
- Falls back to **mock data** when `APIFY_TOKEN` is empty (for local development)

### `ImageClassifierService` (`services/image_classifier.py`)

Classifies property photos using GPT-4o-mini:

- Sends each image with a Portuguese prompt asking "what room is this?"
- Maps responses to `RoomType` enum (cozinha, sala, quarto, casa_de_banho, etc.)
- Runs concurrently with a semaphore (5 max) to avoid rate limits
- Groups classified images by room so multiple photos of the same kitchen = 1 kitchen

### `RenovationEstimatorService` (`services/renovation_estimator.py`)

Estimates renovation costs using GPT-4o Vision:

- Analyzes up to 6 photos per room at `high` detail
- Returns itemized costs with Portuguese market prices (2024/2025)
- Assesses condition (excelente → necessita remodelacao total)
- Confidence score increases with more photos
- Fallback estimates if GPT fails (conservative ranges by room type)
- Generates a final summary contextualizing costs vs. property price

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Install

```bash
cd backend
uv sync
```

### Environment

```bash
cp .env.example .env
# Edit .env with your keys
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o/GPT-4o-mini |
| `APIFY_TOKEN` | No | Apify token. Uses mock data if empty. |
| `SUPABASE_URL` | No | Supabase URL (for future auth) |
| `SUPABASE_ANON_KEY` | No | Supabase anon key |
| `SUPABASE_PASSWORD` | No | Supabase password |
| `DEBUG` | No | Enable debug mode (default: false) |
| `CORS_ORIGINS` | No | Allowed CORS origins (default: `["http://localhost:3000"]`) |

### Run

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Server starts at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Test

```bash
# All tests
cd backend && uv run pytest -v

# Unit tests only
uv run pytest tests/unit/ -v

# Specific file
uv run pytest tests/unit/test_idealista.py -v
```

### Lint

```bash
cd backend && uv run ruff check .
```

## Notebooks

Interactive Jupyter notebooks for testing and debugging the LangGraph pipeline.

### Setup

Install notebook dependencies:

```bash
cd backend
uv sync --extra notebook
```

### Available Notebooks

#### `notebooks/renovation_graph.ipynb`

Test individual nodes of the renovation estimation pipeline.

**Features:**
- Run nodes individually or full graph end-to-end
- **Fixture mode**: Offline testing with realistic mock data (no API keys needed)
- **Live mode**: Real API calls to OpenAI/Apify
- Helper functions to inspect state at each step
- Graph visualization

**Usage:**

1. Open in VS Code or Jupyter:
   ```bash
   cd backend
   code notebooks/renovation_graph.ipynb
   ```

2. Select the `.venv` Python kernel

3. Set mode in cell 2:
   ```python
   MODE = "fixture"  # or "live"
   ```

4. Run cells sequentially to execute each node

**Why use this:**
- Test nodes in isolation without running the full pipeline
- Debug intermediate state between nodes
- Iterate on prompts without re-running expensive steps
- No API costs in fixture mode

### Fixtures

The `notebooks/fixtures.py` module provides realistic state snapshots:

```python
from fixtures import get_state_after

# Get state at any pipeline stage
state = get_state_after("scrape")     # After scraping
state = get_state_after("classify")   # After classification
state = get_state_after("estimate")   # After estimation
```

All fixtures use real Pydantic models with hardcoded realistic values.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| Validation | Pydantic v2, pydantic-settings |
| AI Pipeline | LangGraph (linear 5-node graph) |
| AI Models | GPT-4o (estimation), GPT-4o-mini (classification) |
| Scraping | Apify (`dz_omar/idealista-scraper-api` standby mode) |
| HTTP | httpx (async) |
| Streaming | SSE via sse-starlette |
| Tests | pytest, pytest-asyncio |
| Linting | ruff |
| Package Manager | uv |
| Notebooks | Jupyter (ipykernel) |
