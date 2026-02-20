# Supabase Auth Integration

## Goal

Add complete authentication to Rehabify using Supabase Auth — JWT verification on the backend and a login/signup page on the frontend — without custom database tables or RLS policies. Usage tracking is deferred.

## Scope

- [X] Backend Supabase async client initialized in lifespan
- [X] `get_current_user` FastAPI dependency (JWT → `AuthenticatedUser`)
- [X] `/api/v1/analyze` and `/api/v1/analyze/sync` endpoints protected
- [X] Health check endpoints remain public
- [X] Frontend Supabase browser/server/middleware clients
- [X] Next.js middleware for session cookie refresh
- [X] `/auth` page with login/signup tabs (Portuguese UI)
- [X] `/auth/callback` route handler for email confirmation
- [X] `useAuth` hook (`user`, `loading`, `signOut`)
- [X] Auth gate on home page: redirect to `/auth` if not logged in when clicking "Analisar"
- [X] URL pre-fill after login via `?url=` query param
- [X] User email + "Sair" button in home page header
- [X] `Authorization: Bearer <token>` header sent from `usePropertyAnalysis`
- [X] Backend unit tests for `get_current_user`
- [X] Backend integration tests for auth-protected endpoints
- [X] Frontend tests for `AuthPage`

## Decisions

| Decision             | Choice                            | Rationale                                                  |
| -------------------- | --------------------------------- | ---------------------------------------------------------- |
| JWT verification     | `supabase.auth.get_user(jwt)`   | Simple network call, always fresh, no local key management |
| Auth UI              | Custom Tailwind form              | Full Portuguese control, matches existing design           |
| Auth gate            | On analyze action                 | Home page stays public                                     |
| After-login redirect | `?redirect=` + `?url=` params | URL pre-fill for good UX                                   |
| Usage tracking       | Deferred                          | No DB tables needed yet                                    |

## Files Changed

### New Files

| File                                        | Purpose                                                                 |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| `backend/app/auth.py`                     | `get_current_user` dependency, `AuthenticatedUser`, `CurrentUser` |
| `frontend/src/lib/supabase/client.ts`     | Browser Supabase client                                                 |
| `frontend/src/lib/supabase/server.ts`     | Server Supabase client                                                  |
| `frontend/src/lib/supabase/middleware.ts` | Session refresh utility                                                 |
| `frontend/src/middleware.ts`              | Next.js middleware (session refresh)                                    |
| `frontend/src/app/auth/page.tsx`          | Login/signup page                                                       |
| `frontend/src/app/auth/callback/route.ts` | Email confirmation code exchange                                        |
| `frontend/src/hooks/useAuth.ts`           | Client auth hook                                                        |
| `backend/tests/unit/test_auth.py`         | Auth dependency unit tests                                              |
| `docs/features/supabase-auth/README.md`   | This file                                                               |

### Modified Files

| File                                          | Changes                                                                         |
| --------------------------------------------- | ------------------------------------------------------------------------------- |
| `backend/app/config.py`                     | `supabase_password` → `supabase_service_role_key`                          |
| `backend/app/main.py`                       | Init async Supabase client in lifespan, store on `app.state.supabase`         |
| `backend/app/api/v1/analyze.py`             | Add `CurrentUser` dep to both endpoints, remove `user_id` from request body |
| `backend/.env.example`                      | Updated Supabase env var names                                                  |
| `frontend/.env.example`                     | Added `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`           |
| `frontend/src/lib/config.ts`                | Added Supabase constants and auth route paths                                   |
| `frontend/src/hooks/usePropertyAnalysis.ts` | Added `Authorization: Bearer` header                                          |
| `frontend/src/app/page.tsx`                 | Auth gate on analyze, user info + logout in header                              |
| `frontend/src/components/UrlInput.tsx`      | Added `defaultValue` prop for URL pre-fill                                    |
| `backend/tests/conftest.py`                 | Added Supabase env vars to test fixture                                         |
| `backend/tests/integration/test_api.py`     | Added `TestAuthProtection` class                                              |
