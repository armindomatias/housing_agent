# Visual Redesign — Root Page

## Goal

Transform the root page from a plain functional UI into a polished SaaS landing page using the **Bold Contrast** design system: dark hero with orange accents on a clean white canvas.

## Design System — Bold Contrast

| Token | Value | Usage |
|-------|-------|-------|
| Primary (CTA) | `#F97316` (orange-500) | Buttons, logo, accents |
| Hero bg | `#0F172A` (slate-950) | Hero section background |
| Page bg | `#FFFFFF` | Content areas |
| Surface | `#F8FAFC` (slate-50) | Card backgrounds |
| Text | `#0F172A` (slate-950) | Body copy |
| Muted | `#64748B` (slate-500) | Secondary text |
| Border | `#E2E8F0` (slate-200) | Dividers, card borders |

## Scope

- [x] Branch `feat/visual-redesign-root-page` created
- [x] Dependencies: `lucide-react`, `class-variance-authority`, `clsx`, `tailwind-merge`, `@radix-ui/react-slot`
- [x] `src/lib/utils.ts` — `cn()` utility
- [x] `components.json` — shadcn/ui config
- [x] `src/components/ui/button.tsx` — shadcn/ui Button with CVA variants
- [x] `src/components/ui/input.tsx` — shadcn/ui Input
- [x] `src/components/ui/card.tsx` — shadcn/ui Card family
- [x] `src/components/ui/badge.tsx` — shadcn/ui Badge
- [x] `src/app/globals.css` — Bold Contrast CSS tokens via `@theme inline`
- [x] `src/components/Navbar.tsx` — Sticky white navbar, orange logo, auth buttons
- [x] `src/components/HowItWorks.tsx` — 3-step cards with Lucide icons
- [x] `src/app/page.tsx` — Dark hero + landing layout restructure
- [x] `src/components/UrlInput.tsx` — Migrated to shadcn/ui Input + Button
- [x] `src/components/ProgressIndicator.tsx` — Orange palette, Card wrapper
- [x] `src/components/ResultsDisplay.tsx` — Slate header, Card/Badge migration
- [x] Fix pre-existing `useSearchParams` Suspense boundary errors in both pages

## Decisions

- **No dark mode** — shipping a polished light theme first; dark mode can be added later with a toggle
- **Bold Contrast palette** — YC-style orange on dark slate creates clear hierarchy and brand identity
- **Suspense wrappers** — `useSearchParams()` in Next.js App Router requires Suspense at the page level; applied minimal inner-component pattern to both `/` and `/auth`
- **CSS variables in `@theme inline`** — required for Tailwind v4 to generate utility classes from the design tokens
- **shadcn/ui components created manually** — avoids interactive CLI issues with Tailwind v4 projects

## Files Changed

| File | Action |
|------|--------|
| `frontend/package.json` | Added 5 dependencies |
| `frontend/components.json` | New — shadcn/ui config |
| `frontend/src/lib/utils.ts` | New — `cn()` utility |
| `frontend/src/components/ui/button.tsx` | New |
| `frontend/src/components/ui/input.tsx` | New |
| `frontend/src/components/ui/card.tsx` | New |
| `frontend/src/components/ui/badge.tsx` | New |
| `frontend/src/app/globals.css` | Rewritten — Bold Contrast tokens |
| `frontend/src/components/Navbar.tsx` | New |
| `frontend/src/components/HowItWorks.tsx` | New |
| `frontend/src/app/page.tsx` | Restructured — dark hero, Suspense wrapper |
| `frontend/src/components/UrlInput.tsx` | Migrated to shadcn/ui |
| `frontend/src/components/ProgressIndicator.tsx` | Palette + Card update |
| `frontend/src/components/ResultsDisplay.tsx` | Slate header + Card/Badge |
| `frontend/src/app/auth/page.tsx` | Minimal Suspense wrapper fix |
| `docs/features/visual-redesign-root-page/README.md` | New |
