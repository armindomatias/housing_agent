# Fix: Floor Plan Images Never Analyzed (Missing GPT Mapping)

## Goal

Fix floor plan images being silently dropped from the analysis pipeline when GPT-4o-mini classifies them via the GPT fallback path.

## Scope

- [x] Add floor plan entries to `GPT_ROOM_TYPE_MAP` in `constants.py`
- [x] Add defensive Apify tag variants to `APIFY_TAG_MAP` in `constants.py`
- [x] Add warning log to `_map_room_type()` for future unmapped GPT responses
- [x] Add unit regression tests for floor plan mapping variants
- [x] Add prompt coverage test to prevent this class of bug from recurring
- [x] Add integration test for `group_node` floor plan URL extraction

## Root Cause

`GPT_ROOM_TYPE_MAP` in `backend/app/constants.py` was missing floor plan entries.

The data flow broke like this:

1. Apify scrapes images. If the tag is unrecognized (or absent), GPT-4o-mini classifies the image.
2. The prompt (`backend/app/prompts/renovation.py`) instructs GPT to return `"planta"` for floor plans.
3. `_map_room_type()` looked up `"planta"` in `GPT_ROOM_TYPE_MAP` — **not found** — defaulted to `RoomType.OTHER`.
4. `group_node` skipped `RoomType.OTHER` (it's in `SKIPPED_ROOM_TYPES`).
5. `floor_plan_urls` stayed `[]`, `estimate_node` skipped floor plan analysis entirely.

The `APIFY_TAG_MAP` correctly mapped `"planta"/"floor_plan"/"floorplan"`, so the tag-based path worked. The GPT fallback path was broken and **silent** — no log was emitted.

## Decisions

| Decision | Rationale |
|---|---|
| Add `"planta"`, `"floor_plan"`, `"floor plan"`, `"floorplan"` to `GPT_ROOM_TYPE_MAP` | These are the exact strings the prompt instructs GPT to return |
| Add `"outro"` / `"other"` explicitly to `GPT_ROOM_TYPE_MAP` | Makes the mapping intentional, not a hidden `.get()` default |
| Add `"plan"`, `"plans"`, `"planimetria"`, `"floor-plan"` to `APIFY_TAG_MAP` | Defensive coverage for Apify tag variants not yet observed |
| Add warning log in `_map_room_type()` when value is unmapped | Makes future mapping gaps immediately visible in logs instead of silently dropping images |
| Add `TestGPTMapPromptCoverage` test | Parses the prompt's room type list and asserts every key is in `GPT_ROOM_TYPE_MAP`; prevents this class of bug from recurring when the prompt is updated |

## Files Changed

| File | Change |
|---|---|
| `backend/app/constants.py` | Added floor plan entries to `GPT_ROOM_TYPE_MAP`; added defensive variants to `APIFY_TAG_MAP` |
| `backend/app/services/image_classifier.py` | Added warning log to `_map_room_type()` for unmapped GPT responses |
| `backend/tests/unit/test_image_classifier.py` | Added `test_maps_floor_plan_variants`, `test_maps_outro_and_other_explicitly`, `TestGPTMapPromptCoverage` |
| `backend/tests/integration/test_group_node.py` | Added `test_group_node_extracts_floor_plan_urls` |
