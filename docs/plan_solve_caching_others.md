# Plan: Issue #1 — Service Lifecycle & Dependency Injection

## Problem
Services are re-instantiated on every graph node execution. Per request: 5 service instantiations, 4 AsyncOpenAI clients, 2 httpx clients. `RenovationEstimatorService` internally couples to `ImageClassifierService` just for `get_room_label()` — a pure function.

## Changes

### Step 1: Extract `get_room_label()` as standalone function
**File:** `backend/app/services/image_classifier.py`
- Move `get_room_label()` out of the class into a module-level function
- Keep it importable from the same module for backwards compat
- Remove the method from the class (no callers use it via instance except `RenovationEstimatorService`)

### Step 2: Remove internal `ImageClassifierService` from `RenovationEstimatorService`
**File:** `backend/app/services/renovation_estimator.py`
- Remove `self._classifier = ImageClassifierService(openai_api_key)` from `__init__`
- Import and use the standalone `get_room_label()` function directly
- Update `analyze_room()` and any other methods that used `self._classifier.get_room_label()`

### Step 3: Create services once in `build_renovation_graph()`, inject via closures
**File:** `backend/app/graphs/main_graph.py`
- Create `IdealistaService`, `ImageClassifierService`, `RenovationEstimatorService` once in `build_renovation_graph()`
- Pass service instances into node functions via keyword args (same pattern as `settings`)
- Update node signatures to accept service instances
- `group_node` uses the standalone `get_room_label()` + `ImageClassifierService.group_by_room()` from the shared instance
- Ensure `IdealistaService` is properly closed after scrape (already done via try/finally)

### Step 4: Update `main_graph.py` node functions to stop instantiating services
- `scrape_node`: receive `idealista_service` param instead of creating one
- `classify_node`: receive `classifier_service` param
- `group_node`: receive `classifier_service` param (for `group_by_room()`)
- `estimate_node`: receive `estimator_service` param
- `summarize_node`: receive `estimator_service` param

### Step 5: Update `estimate_node` to use standalone `get_room_label()`
**File:** `backend/app/graphs/main_graph.py`
- Replace `estimator._classifier.get_room_label()` with direct `get_room_label()` call

### Step 6: Update tests
- Unit tests for `get_room_label()` as standalone function (should still pass as-is)
- Verify existing tests still pass

## Files Changed
1. `backend/app/services/image_classifier.py` — extract `get_room_label()`
2. `backend/app/services/renovation_estimator.py` — remove internal classifier coupling
3. `backend/app/graphs/main_graph.py` — service injection via closures
4. `backend/tests/unit/test_image_classifier.py` — update if needed for standalone function

## Not Changed
- Models, prompts, API layer, frontend — no changes needed
