# Feature: Floor Plan Analysis

**Branch:** `feat/floor-plan-analysis`
**Status:** Completed (backend only)
**Date:** 2026-02-20

## Goal

Instead of silently dropping floor plan ("planta") images from the Apify scrape, detect them, send them to GPT-4o, and return structured layout improvement ideas as part of the renovation estimate.

## Scope

- [x] Add `FLOOR_PLAN` as a first-class `RoomType` enum value
- [x] Add `FloorPlanIdea` and `FloorPlanAnalysis` Pydantic models
- [x] Extend `RenovationEstimate` with `floor_plan_ideas: FloorPlanAnalysis | null`
- [x] Map Apify tags (`"planta"`, `"floor_plan"`, `"floorplan"`) to `FLOOR_PLAN`
- [x] Extract floor plan URLs in the group node instead of discarding them
- [x] Analyse floor plans concurrently with room estimates in the estimate node
- [x] Add `FLOOR_PLAN_ANALYSIS_PROMPT` (Portuguese) for GPT-4o
- [ ] Frontend card — deferred; reverted after initial implementation

## How It Works

### Classification

`image_classifier.py` maps the Apify `roomType` field. The three known floor-plan tag variants are all normalised to `RoomType.FLOOR_PLAN`:

```
"planta" | "floor_plan" | "floorplan"  →  RoomType.FLOOR_PLAN
```

`FLOOR_PLAN` is also added to `IMAGE_CLASSIFICATION_PROMPT` so the GPT-4o-mini classifier can assign it when Apify provides no tag.

### Graph State

Two new fields are added to `GraphState`:

| Field | Type | Purpose |
|---|---|---|
| `floor_plan_urls` | `list[str]` | Image URLs identified as floor plans |
| `floor_plan_analysis` | `FloorPlanAnalysis \| None` | Result from `analyze_floor_plan()` |

### Group Node

Previously, `FLOOR_PLAN`-type images were silently dropped during grouping. Now `group_node` collects them into `state["floor_plan_urls"]` before processing room clusters.

### Estimate Node

`analyze_floor_plan()` runs **concurrently** with the per-room estimation tasks via `asyncio.gather`, so it adds no wall-clock latency to the overall pipeline.

`analyze_floor_plan()`:
1. Encodes all floor plan images as base64 and sends them to GPT-4o in a single call with `FLOOR_PLAN_ANALYSIS_PROMPT`.
2. Parses the JSON response into a `FloorPlanAnalysis` object containing:
   - `ideas` — list of `FloorPlanIdea` (title, description, potential_impact, estimated_complexity)
   - `property_context` — GPT's one-line summary of the layout
   - `confidence` — 0–1 float
   - `images` — the URLs that were analysed
3. Returns `None` if there are no floor plan URLs, or on any parse/API error (logged at WARNING level).

### Summarize Node / Create Estimate

`floor_plan_analysis` is forwarded through `summarize_node` into `create_estimate()`, which sets `RenovationEstimate.floor_plan_ideas`.

## New Models (`backend/app/models/property.py`)

| Model | Purpose |
|---|---|
| `FloorPlanIdea` | One layout idea: `title`, `description`, `potential_impact`, `estimated_complexity` (`"baixa"` / `"media"` / `"alta"`) |
| `FloorPlanAnalysis` | Full result: `images[]`, `ideas[]`, `property_context`, `confidence` |

## Files Changed

| File | Change |
|---|---|
| `backend/app/models/property.py` | Add `FloorPlanIdea`, `FloorPlanAnalysis`; add `FLOOR_PLAN` to `RoomType`; add `floor_plan_ideas` to `RenovationEstimate` |
| `backend/app/services/image_classifier.py` | Map `"planta"` / `"floor_plan"` / `"floorplan"` to `FLOOR_PLAN`; add label in `get_room_label()` |
| `backend/app/prompts/renovation.py` | Add `FLOOR_PLAN_ANALYSIS_PROMPT`; update `IMAGE_CLASSIFICATION_PROMPT` |
| `backend/app/services/renovation_estimator.py` | Add `analyze_floor_plan()`; update `create_estimate()` to accept and forward `floor_plan_analysis` |
| `backend/app/graphs/state.py` | Add `floor_plan_urls` and `floor_plan_analysis` fields |
| `backend/app/graphs/main_graph.py` | Extract floor plan URLs in `group_node`; run `analyze_floor_plan()` concurrently in `estimate_node`; thread result through `summarize_node` |
| `backend/tests/unit/test_image_classifier.py` | Tests for new tag mappings and label |
| `backend/tests/unit/test_models.py` | Update enum count assertion |
| `backend/tests/unit/test_renovation_estimator.py` | Tests for `analyze_floor_plan()` (success, empty, error paths) and updated `create_estimate()` |

## Decisions

| Decision | Reason |
|---|---|
| Concurrent execution with room estimates | Floor plan analysis is independent; running it in parallel avoids adding latency |
| GPT-4o (not mini) for floor plan analysis | Layout reasoning from an architectural image requires stronger vision capability |
| Return `None` on missing floor plans | Keeps `RenovationEstimate` stable for properties without floor plan images |
| Single batch call with all floor plan images | Most listings have only 1–2 floor plan images; batching keeps cost low |
| Frontend card deferred | Backend shipped first for end-to-end data validation; UI reverted pending final design decision |
