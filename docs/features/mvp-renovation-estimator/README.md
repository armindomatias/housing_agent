# Feature: MVP Renovation Estimator

**Branch:** `main` (initial implementation)
**Status:** Completed
**Date Started:** 2025-01

## Goal

Allow first-time home buyers in Portugal to paste an Idealista property URL and receive an AI-generated renovation cost estimate, broken down by room.

## Scope

- [x] Scrape property data from Idealista via Apify
- [x] Classify property images by room type using GPT-4o-mini
- [x] Group images by room to avoid duplicate estimates
- [x] Estimate renovation costs per room using GPT-4o
- [x] Generate executive summary in Portuguese
- [x] Stream progress to frontend via SSE
- [x] Display results with room-by-room breakdown

## Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| LangGraph with dict state | Simple linear pipeline; dict state is easier to debug than typed state for MVP | 2025-01 |
| GPT-4o-mini for classification | Fast and cheap for simple room-type identification; GPT-4o overkill for this step | 2025-01 |
| GPT-4o for estimation | Needs high-quality vision analysis for accurate condition assessment and cost ranges | 2025-01 |
| SSE over WebSockets | Simpler to implement; unidirectional stream is sufficient (client doesn't send messages during analysis) | 2025-01 |
| Apify for scraping | Legal compliance — third-party service handles scraping; easy to swap actors | 2025-01 |
| Mock data fallback | Allows frontend development without Apify token; returns realistic sample data | 2025-01 |
| Portuguese prompts | Target market is Portugal; Portuguese prompts produce better PT-PT output from GPT | 2025-01 |
| Min/max cost ranges | Single-point estimates are misleading for renovation; ranges set better expectations | 2025-01 |

## Files Changed

### Backend
- `app/main.py` — FastAPI application with CORS, lifespan, health checks
- `app/config.py` — Settings via pydantic-settings (API keys, model config)
- `app/models/property.py` — All domain models (RoomType, PropertyData, RenovationEstimate, StreamEvent)
- `app/services/idealista.py` — Apify-based Idealista scraper with mock fallback
- `app/services/image_classifier.py` — GPT-4o-mini image classification with rate limiting
- `app/services/renovation_estimator.py` — GPT-4o room analysis and cost estimation
- `app/graphs/state.py` — LangGraph state definition
- `app/graphs/main_graph.py` — 5-node pipeline (scrape → classify → group → estimate → summarize)
- `app/prompts/renovation.py` — AI prompt templates in Portuguese
- `app/api/v1/analyze.py` — SSE streaming endpoint + sync fallback

### Frontend
- `src/app/page.tsx` — Main page with workflow steps and conditional rendering
- `src/app/layout.tsx` — Root layout with Portuguese metadata
- `src/components/UrlInput.tsx` — URL input with Idealista validation
- `src/components/ProgressIndicator.tsx` — Step-by-step progress display
- `src/components/ResultsDisplay.tsx` — Room-by-room results with cost formatting
- `src/hooks/usePropertyAnalysis.ts` — SSE streaming hook
- `src/types/analysis.ts` — TypeScript types mirroring backend models
