# Rehabify - Project Context

## Language Rules

- **ALL code, files, folders, variables, functions, classes, comments**: English
- **AI prompts (for Claude API), user-facing text, UI labels**: Portuguese (Portugal)
- **This documentation**: English

## What Is This

Conversational web application to help first-time home buyers in Portugal:

- Analyze properties from Idealista
- Estimate renovation costs via AI photo analysis
- Calculate taxes and fiscal incentives, based on their fiscal persona and objectives
- Compare investments

## Git Workflow

### Branch Strategy

ALWAYS create a new branch before making any code changes. Never commit directly to `main`.

### Branch Naming Convention

Use this format: `<type>/<short-description>`

Types:

- `feat/` - New feature (e.g., `feat/add-pdf-generation`)
- `fix/` - Bug fix (e.g., `fix/streaming-not-working`)
- `refactor/` - Code refactoring (e.g., `refactor/extract-tax-calculator`)
- `docs/` - Documentation (e.g., `docs/update-readme`)
- `test/` - Tests (e.g., `test/add-imt-calculation-tests`)
- `chore/` - Maintenance (e.g., `chore/update-dependencies`)

### Workflow Steps

1. **Before starting any task**, create and checkout a new branch:

```bash
   git checkout main
   git pull origin main  # if remote exists
   git checkout -b <type>/<description>
```

2. **Make commits** with clear messages:

```bash
   git add <files>
   git commit -m "<type>: <description>"
```

   Commit message examples:

- `feat: add IMT calculation for primary residence`
- `fix: correct streaming event format`
- `refactor: extract room analysis into separate function`

3. **When task is complete**, inform me that the branch is ready for review:

```
   ✅ Branch `feat/add-pdf-generation` is ready for review.
   
   Changes:
   - Added PDF generation service
   - Created report template
   - Added endpoint POST /api/reports
   
   To review: git diff main..feat/add-pdf-generation
   To merge: git checkout main && git merge feat/add-pdf-generation
```

### Rules

- NEVER commit directly to `main`
- NEVER force push
- Create atomic commits (one logical change per commit)
- If a task is complex, break it into multiple commits
- Always check current branch before making changes: `git branch --show-current`

## Architecture Overview

### Monorepo Structure

```
housing_agent/
├── backend/                  # Python FastAPI + LangGraph
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Settings (pydantic-settings)
│   │   ├── api/v1/           # Routers (one per endpoint group)
│   │   ├── models/           # Pydantic models
│   │   ├── services/         # Business logic (one service per file)
│   │   ├── graphs/           # LangGraph pipelines
│   │   ├── prompts/          # AI prompt templates
│   │   └── agents/           # Future agent definitions
│   └── tests/                # pytest suite
│       ├── conftest.py       # Shared fixtures
│       ├── unit/             # Pure logic tests
│       ├── integration/      # API/graph tests
│       └── regression/       # Bug-fix regression tests
├── frontend/                 # Next.js + TypeScript + Tailwind
│   └── src/
│       ├── app/              # Next.js app router pages
│       ├── components/       # React components
│       ├── hooks/            # Custom React hooks
│       ├── types/            # TypeScript type definitions
│       └── __tests__/        # Vitest test suite
├── docs/features/            # Feature documentation (git-tracked)
└── .claude/                  # Claude Code config (gitignored)
    ├── CLAUDE.md             # This file
    └── commands/             # Custom slash commands
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, Pydantic v2, LangGraph |
| AI | OpenAI GPT-4o (estimation), GPT-4o-mini (classification) |
| Scraping | Apify (Idealista actor) |
| Frontend | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| Streaming | Server-Sent Events (SSE) via sse-starlette |

### Data Flow (LangGraph Pipeline)

```
scrape (Apify) → classify (GPT-4o-mini) → group (pure logic) → estimate (GPT-4o) → summarize (GPT-4o)
```

Each node emits `StreamEvent`s that flow to the frontend via SSE.

### Run Commands

```bash
# Backend
cd backend && uv run uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Tests
cd backend && uv run pytest -v
cd frontend && npm run test:run

# Linting
cd backend && uv run ruff check .
cd frontend && npm run lint
```

## Feature Development Workflow

Every feature follows this 7-step sequence:

### 1. Understand

Read the requirements. If anything is unclear, ask before writing code.

### 2. Plan

Identify which files to create/modify. Check existing patterns in the codebase. Write a brief plan before implementation.

### 3. Branch

```bash
git checkout main && git checkout -b feat/<feature-name>
```

### 4. Build

Follow these isolation principles:
- One service per file in `backend/app/services/`
- One router per endpoint group in `backend/app/api/v1/`
- One component per file in `frontend/src/components/`
- Models in `backend/app/models/` — group by domain

### 5. Test

Write tests alongside code, not after:
- Unit tests for every service, model, and utility
- Integration tests for API endpoints
- See **Testing Standards** below

### 6. Document

Create/update the feature doc in `docs/features/<feature-name>/README.md` with:
- Goal, Scope checklist, Decisions log, Files Changed

### 7. Review

Use `/feature-done` to run full test suite and generate review summary.

## Testing Standards

### Test Types

| Type | When | Mocking |
|------|------|---------|
| Unit | Every service, model, utility | No external calls. Mock OpenAI, Apify, DB. |
| Integration | API endpoints, graph flows | Mock external services. Use FastAPI TestClient. |
| Regression | Bug fixes | Reproduce the bug as a failing test first, then fix. |

### Directory Layout

```
backend/tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_models.py       # Pydantic model validation
│   ├── test_idealista.py    # URL validation, ID extraction
│   └── test_image_classifier.py  # Room mapping, grouping
├── integration/
│   └── test_api.py          # Endpoint tests via TestClient
└── regression/              # Bug-fix tests

frontend/src/__tests__/
├── setup.ts                 # jest-dom matchers
└── components/
    └── UrlInput.test.tsx    # Component tests
```

### Naming Conventions

- Files: `test_<module>.py` (backend), `<Component>.test.tsx` (frontend)
- Functions: `test_<what>_<expected>` e.g. `test_validate_url_rejects_non_idealista`
- Group related tests in classes: `class TestValidateUrl:`

### Run Commands

```bash
# All backend tests
cd backend && uv run pytest -v

# Specific test file
cd backend && uv run pytest tests/unit/test_models.py -v

# Frontend tests
cd frontend && npm run test:run

# Watch mode (frontend)
cd frontend && npm run test
```

## Code Quality Standards

### Python (Backend)

- **Type hints**: All function signatures must include type hints
- **Linting**: Run `uv run ruff check .` before every commit
- **Async**: Use `async/await` for all I/O operations (HTTP, OpenAI, DB)
- **Imports**: Use absolute imports from `app.` (not relative)

### TypeScript (Frontend)

- **No `any`**: Use proper types. Define interfaces for component props.
- **`"use client"`**: Only on components that use React hooks or browser APIs
- **Props**: Define as interfaces above the component

### General

- **No magic numbers**: Use named constants or config values
- **File size**: Keep files under 300 lines. Split if larger.
- **Error messages**: User-facing messages in Portuguese, logs in English
