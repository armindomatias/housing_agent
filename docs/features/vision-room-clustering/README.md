# Feature: GPT Vision Room Clustering

**Branch:** `feat/vision-room-clustering`
**Status:** Completed
**Date:** 2026-02-18

## Goal

Replace the naive room grouping (which assumed every photo of the same type belonged to the same physical room) with a GPT-4o-mini vision-based approach that compares images visually to determine which photos show the same physical room. This produces more accurate per-room renovation estimates when a property has multiple bedrooms or bathrooms.

## Problem with the Old Approach

`group_by_room_simple()` bucketed all images by their Apify-assigned `room_type` tag. A property with 3 bedrooms would have all bedroom photos lumped into one `quarto_1` group, causing the estimator to produce a single blended estimate instead of separate estimates for each physical room.

## Solution

A two-pass algorithm in `group_by_room()` (async):

### Pass 1 — Bucket by room type

All classified images are grouped by `room_type`, ignoring the existing `room_number` from Apify metadata.

### Pass 2 — Vision clustering for multi-room types

For room types that can appear more than once (`BEDROOM`, `BATHROOM`), if there is more than one image in the bucket, `cluster_room_images()` is called:

1. All images of that type are sent to GPT-4o-mini in **one batch call** with the `ROOM_CLUSTERING_PROMPT`, so the model can compare visual cues (furniture, walls, flooring, fixtures) across photos.
2. GPT returns a `ClusteringResult` JSON with a list of `RoomCluster` objects, each containing the image indices that belong to the same physical room.
3. Clustering tasks for all multi-room types run **concurrently** via `asyncio.gather`.

For singleton types (kitchen, living room, etc.) the room number stays at 1.

### Fallbacks

| Situation | Fallback |
|---|---|
| Only 1 image in the bucket | Single cluster, confidence=1.0, no API call |
| GPT returns invalid/overlapping clusters | `_validate_clusters()` drops bad clusters; missing images appended to the last cluster |
| Any API or parse error | `_metadata_fallback()` splits images evenly across `num_rooms`/`num_bathrooms` from property metadata |
| Metadata also unavailable | All images in one group |

**Under-grouping is preferred over over-grouping** — the prompt instructs GPT to merge ambiguous photos into an existing room rather than create a new one, avoiding muddled estimates.

### Bug Fix: Null OpenAI Content (`fix: handle null OpenAI content in room analysis`)

GPT-4o occasionally returns `content=None` (content filter / refusal). This caused `json.loads(None)` to raise a `TypeError` which fell through to a broad `except Exception` handler, logging a misleading ERROR. The fix explicitly checks for `None` before calling `json.loads` and falls back to the conservative estimate at `WARNING` level.

## New Models (`backend/app/models/property.py`)

| Model | Purpose |
|---|---|
| `RoomCluster` | One physical room: `room_number`, `image_indices`, `confidence`, `visual_cues` |
| `ClusteringResult` | Full GPT response: `clusters[]`, `total_rooms`, `reasoning` |

## Files Changed

| File | Change |
|---|---|
| `backend/app/services/image_classifier.py` | Add `cluster_room_images()`, `_validate_clusters()`, `_metadata_fallback()`, async `group_by_room()`; keep `group_by_room_simple()` for reference |
| `backend/app/models/property.py` | Add `RoomCluster` and `ClusteringResult` models |
| `backend/app/prompts/renovation.py` | Add `ROOM_CLUSTERING_PROMPT` (Portuguese) |
| `backend/app/graphs/main_graph.py` | Update `group_node` to await async `group_by_room` and pass `num_rooms`/`num_bathrooms` |
| `backend/app/services/renovation_estimator.py` | Guard against `content=None` from OpenAI before `json.loads` |
| `backend/tests/unit/test_image_classifier.py` | 67 new tests: `TestValidateClusters`, `TestMetadataFallback`, `TestClusterRoomImages`, `TestGroupByRoomAsync` |
| `backend/tests/integration/test_group_node.py` | Integration tests for the updated group node |

## Decisions

| Decision | Reason |
|---|---|
| GPT-4o-mini for clustering (not GPT-4o) | Vision clustering is a simpler visual-similarity task; mini is cheaper and fast enough |
| Single batch call per room type | Lets GPT compare all images at once for better consistency vs. pairwise calls |
| Prefer under-grouping | A slightly merged estimate is less harmful than a completely split one with wrong room counts |
| Keep `group_by_room_simple()` | Useful reference and fallback during testing without incurring API costs |
| `asyncio.gather` for concurrent clustering | Bedrooms and bathrooms can be clustered in parallel; reduces total latency |
