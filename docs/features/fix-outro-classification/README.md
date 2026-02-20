# Fix "outro" Classification: Force GPT to Commit to Dominant Room Type

## Goal

Reduce the number of images silently dropped from renovation estimation due to over-classification as "outro" (other). Mixed spaces, bad-condition rooms, and ambiguous habitable areas were previously escaping into `SKIPPED_ROOM_TYPES`, losing valuable data for the user.

## Scope

- [x] Tighten the classification prompt so GPT must commit to the dominant room type
- [x] Reserve "outro" strictly for genuinely non-room images (logos, marketing graphics)
- [x] Fix `office` Apify tag mapping from `OTHER` → `BEDROOM`
- [x] Add unit test for `office` tag mapping
- [x] Document the change

## Problem

The prompt gave GPT an easy escape hatch: `outro: Não identificável ou espaço misto`. This caused:
- Mixed spaces (living/dining combos) → classified as "outro" → skipped
- Rooms in bad condition but recognisable → classified as "outro" → skipped
- Apify-tagged "office" images → mapped to `RoomType.OTHER` → skipped

All skipped rooms produced no renovation estimate, losing data the user needed.

## Decisions

| Decision | Rationale |
|----------|-----------|
| "Outro" redefined to logos/graphics only | The only genuinely non-classifiable images are non-room images; everything else has a dominant type |
| Ambiguous habitable space → "sala" | Living room is the most common and versatile fallback; beats dropping the data |
| `office` → `BEDROOM` (not `OTHER`) | In Portuguese real estate, an escritório is renovated like a quarto; mapping to OTHER silently discarded the image |
| No change to `SKIPPED_ROOM_TYPES` | Exterior and Other are still correctly skipped; the fix is upstream (fewer misclassifications reach "outro") |

## Files Changed

| File | Change |
|------|--------|
| `backend/app/prompts/renovation.py` | Rewrote "outro" description; added `REGRAS IMPORTANTES` section with mixed-space, bad-condition, and ambiguous-space rules |
| `backend/app/constants.py` | Changed `"office"` entry in `APIFY_TAG_MAP` from `RoomType.OTHER` → `RoomType.BEDROOM` |
| `backend/tests/unit/test_image_classifier.py` | Added `test_office_tag_maps_to_bedroom` in `TestClassifyFromTag` |

## Verification

```bash
# Run tests
cd backend && uv run pytest -v

# Run linter
cd backend && uv run ruff check .
```

Manual smoke test: run the pipeline against a property with mixed-space photos and verify those rooms appear in the estimation results instead of being silently dropped.
