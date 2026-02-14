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
