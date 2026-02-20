# Feature: Extract Hardcoded Values to Config & Constants

**Branch:** `chore/extract-hardcoded-to-config`
**Status:** Completed
**Date:** 2026-02-20

## Goal

Centralize 40+ backend and 15+ frontend hardcoded values into dedicated
configuration and constants files, making it easy to tune operational
parameters and find business logic constants without hunting through service files.

## Scope

- [x] Create `backend/app/constants.py` — business logic constants (mappings, thresholds, labels)
- [x] Extend `backend/app/config.py` — nested Pydantic models for operational params
- [x] Update `backend/app/services/image_classifier.py` — use config + constants
- [x] Update `backend/app/services/image_downloader.py` — use config + constants
- [x] Update `backend/app/services/renovation_estimator.py` — use config + constants
- [x] Update `backend/app/services/idealista.py` — use config
- [x] Update `backend/app/main.py` — use constants, pass config to services
- [x] Update `backend/app/graphs/main_graph.py` — use constants
- [x] Create `frontend/src/lib/config.ts` — frontend constants
- [x] Update `frontend/src/hooks/usePropertyAnalysis.ts` — use config
- [x] Update `frontend/src/components/ProgressIndicator.tsx` — use config
- [x] Update `frontend/src/components/ResultsDisplay.tsx` — use config
- [x] Update `frontend/src/components/UrlInput.tsx` — use config
- [x] Update `frontend/src/app/layout.tsx` — use config
- [x] Update `backend/.env.example` — document new env vars
- [x] Update `.claude/CLAUDE.md` — add config rules and mandatory docs rule

## Decisions

| Decision | Reason |
|---|---|
| `config.py` + `constants.py` split | Clean separation: env-overridable operational params vs fixed business logic |
| Nested Pydantic `BaseModel` groups | Type-safe, validated, env-overridable via `__` delimiter (e.g. `APIFY__MAX_RETRIES=5`) |
| `env_nested_delimiter="__"` | Standard pydantic-settings pattern for nested model env-var injection |
| `frontend/src/lib/config.ts` (not env vars) | Display constants don't change per environment — env vars would be overkill |
| Keep `image_detail` as method parameter | `cluster_room_images` and `group_by_room` already expose it as an API; config provides the *default* classification detail via `openai_config.classification_detail` |
| `SKIPPED_ROOM_TYPES` as `frozenset[str]` | Matches usage pattern in `group_node` where `room_type` is already a `.value` string |
| No i18n extraction | Portuguese strings left inline — separate task to avoid scope creep |

## Files Changed

| File | Action |
|------|--------|
| `backend/app/constants.py` | **Create** — business constants |
| `backend/app/config.py` | **Modify** — add `OpenAIConfig`, `ImageProcessingConfig`, `ApifyConfig` nested models |
| `backend/app/services/image_classifier.py` | **Modify** — use config + constants; remove inline dicts |
| `backend/app/services/image_downloader.py` | **Modify** — add constructor, use config + constants |
| `backend/app/services/renovation_estimator.py` | **Modify** — use config + constants |
| `backend/app/services/idealista.py` | **Modify** — use `ApifyConfig` |
| `backend/app/main.py` | **Modify** — use `API_TITLE`, `API_VERSION`; pass config to services |
| `backend/app/graphs/main_graph.py` | **Modify** — use `PIPELINE_TOTAL_STEPS`, `SKIPPED_ROOM_TYPES` |
| `backend/.env.example` | **Modify** — document new optional env vars |
| `frontend/src/lib/config.ts` | **Create** — frontend constants |
| `frontend/src/hooks/usePropertyAnalysis.ts` | **Modify** — use config |
| `frontend/src/components/ProgressIndicator.tsx` | **Modify** — use config |
| `frontend/src/components/ResultsDisplay.tsx` | **Modify** — use config |
| `frontend/src/components/UrlInput.tsx` | **Modify** — use config |
| `frontend/src/app/layout.tsx` | **Modify** — use config |
| `.claude/CLAUDE.md` | **Modify** — add config rules + mandatory docs rule |
| `docs/features/extract-hardcoded-to-config/README.md` | **Create** — this file |
