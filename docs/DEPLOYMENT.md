# Deployment Guide

A practical runbook for deploying the School AI Grade & Report-Card system. It
reflects the Phase 0A/0B deployment-prep changes already in the repo:
`psycopg[binary]` for PostgreSQL, `.python-version` pinned to 3.12, a production
JWT guard in `auth.py`, `frontend/netlify.toml` (with `/api` rewrite + SPA
fallback), and in-memory PDF regeneration on download.

> Scope: this is a student/demo-grade deployment. It is not a hardened
> production setup (no rate limiting, JWT lives in `localStorage`, etc.).

## 1. Recommended architecture

```
            ┌──────────────────────────┐
Browser ───▶│ Netlify (static frontend)│
            │  /api/*  ─── rewrite ────────────▶ Render (FastAPI backend)
            │  /*      ─── index.html  │            │
            └──────────────────────────┘            ▼
                                          Render Postgres  /  Neon (PostgreSQL)
```

- **Backend:** FastAPI on **Render** (web service), served by `uvicorn`.
- **Database:** **Render PostgreSQL** (co-located) or **Neon** (free tier).
- **Frontend:** static Vite build on **Netlify**.
- **Same-origin via rewrite:** Netlify proxies `/api/*` to the backend, so the
  browser only talks to its own origin. **No CORS configuration is needed** and
  the frontend's hardcoded `'/api/v1'` base works unchanged.

## 2. Backend environment variables

Set these on the Render service (Environment tab). The app loads `backend/.env`
locally, but on the platform you set real env vars (platform values win).

| Variable | Required | Example / default | Notes |
|----------|----------|-------------------|-------|
| `APP_ENV` | ✅ | `production` | Activates the production JWT guard. (Also accepts `ENVIRONMENT`.) |
| `DATABASE_URL` | ✅ | `postgresql+psycopg://user:pass@host:5432/dbname` | **Must** use the `postgresql+psycopg://` prefix (see §6). |
| `JWT_SECRET_KEY` | ✅ | a long random string | **Never** the default `change-me-before-production`; with `APP_ENV=production` the app refuses to start otherwise. |
| `APP_BASE_URL` | email only | `https://your-site.netlify.app` | The deployed **frontend** URL. Required only when using report-notification emails. |
| `JWT_ALGORITHM` | optional | `HS256` (default) | Leave unset unless changing. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | optional | `60` (default) | Token lifetime. |
| `OPENAI_API_KEY` | optional | — | Only needed to enable AI summaries. |
| `OPENAI_MODEL` | optional | `gpt-4o-mini` (default) | — |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` | email only | `SMTP_PORT=587` | Required only when using report email sending. |

`APP_BASE_URL` and the `SMTP_*` variables are validated only when the admin
uses the report-send workflow. The app can boot and run without them.

Generate a secret, e.g.: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## 3. Backend build / start commands

Configure the Render web service with **Root Directory = `backend`**:

```bash
# Build
pip install -r requirements.txt

# Start  (Render provides $PORT)
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Python version:** the repo pins `3.12` in `/.python-version` (repo root). If
your service Root Directory is `backend/`, also set **`PYTHON_VERSION=3.12`** as
an env var (or place a `.python-version` in `backend/`) so the build picks it up.
Python 3.14 (used locally) is not yet supported on most build images.

## 4. Database migration command

Run migrations **before first use and on every deploy that adds migrations**,
with `DATABASE_URL` set, from the `backend/` directory:

```bash
alembic upgrade head
```

On Render, set this as a **Pre-Deploy Command** (or run it once in a shell). It
creates all tables from the single migration `ba9dbad0d63e_create_initial_tables`.
(The JWT guard does not block migrations — Alembic does not import `auth`.)

## 5. Frontend build settings (Netlify)

Connect the repo and set:

| Setting | Value |
|---------|-------|
| Base directory | `frontend` |
| Build command | `npm run build` |
| Publish directory | `dist` |

These match `frontend/netlify.toml`, which also defines the routing:

```toml
[[redirects]]            # API proxy → backend (keeps same-origin, no CORS)
  from = "/api/*"
  to = "https://YOUR-BACKEND-URL.example.com/api/:splat"
  status = 200
  force = true

[[redirects]]            # SPA fallback so deep links / refresh work
  from = "/*"
  to = "/index.html"
  status = 200
```

🔴 **Before deploying, edit `frontend/netlify.toml` and replace
`https://YOUR-BACKEND-URL.example.com` with your real Render backend origin.**
Netlify does not expand environment variables inside a redirect `to`, so the URL
must be hardcoded here. The `/api/*` rule must stay **above** the `/*` fallback.

## 6. PostgreSQL notes

- **Use the `postgresql+psycopg://` URL scheme.** The app installs psycopg 3
  (`psycopg[binary]`). A bare `postgresql://…` makes SQLAlchemy default to the
  psycopg2 dialect → `ModuleNotFoundError: psycopg2`. Managed providers often
  hand out `postgres://…` or `postgresql://…` — rewrite the scheme to
  `postgresql+psycopg://…` (keep the rest of the URL).
- **Run migrations before use** (`alembic upgrade head`, §4). The models are
  portable (UUID/JSON/`func.now()` work on PostgreSQL).

## 7. PDF behavior (important for deployment)

- **PDF downloads are regenerated in memory** on each request to
  `GET /api/v1/reports/{id}/pdf`, rebuilt from the stored `ReportCard` +
  `ReportCardCourse` snapshot. **No file on disk is required to download.**
- You therefore **do not need a persistent disk** for report downloads — this is
  what makes the app safe on Render's ephemeral filesystem.
- Report **generation** still writes a PDF under `backend/storage/pdfs/` and
  stores its path in `pdf_url`. That file is now just a local artifact; it is not
  used for downloads and need not survive a redeploy. `pdf_url` is retained for
  backward compatibility and is not load-bearing.

## 8. Demo data script

Populates a full, clickable demo (linked parent/student, a course with grades, an
approved report card + PDF). Run from `backend/` with `DATABASE_URL` set:

```bash
cd backend
python scripts/create_demo_data.py
```

Demo accounts (all password `dev-password-123`):
`demo-parent@school.test`, `demo-teacher@school.test`, `demo-admin@school.test`.

> ⚠️ **Warning:** the script writes demo users and records into whatever
> `DATABASE_URL` points at. Only run it against a **demo** deployment's database —
> never against a real production database with real users. The demo passwords are
> well-known and for demonstration only.

## 9. Post-deploy checks

Replace `BACKEND` / `SITE` with your URLs.

1. **Health:** `GET https://BACKEND/health` → `200 {"status":"ok"}`.
2. **API docs:** open `https://BACKEND/docs` (Swagger UI loads).
3. **Login:**
   ```bash
   curl -X POST https://SITE/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"demo-admin@school.test","password":"dev-password-123"}'
   ```
   (Through the Netlify origin → exercises the `/api` rewrite.) Expect a token.
4. **Frontend:** open `https://SITE`, sign in as each demo role; refresh on a deep
   link (e.g. `/admin/students`) to confirm the SPA fallback works (no 404).
5. **Parent report download:** as the demo parent, open the report and click
   **Download PDF** → a PDF downloads (regenerated, no disk dependency).
6. **Admin audit logs:** as the demo admin, open `/admin/audit-logs` → entries load.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Backend crashes on boot: `RuntimeError: JWT_SECRET_KEY must be set to a non-default value…` | `APP_ENV=production` with a blank/default `JWT_SECRET_KEY` | Set a strong `JWT_SECRET_KEY` env var. |
| `ModuleNotFoundError: No module named 'psycopg2'` (or dialect errors) | `DATABASE_URL` uses `postgresql://` / `postgres://` | Use the `postgresql+psycopg://…` scheme (§6). |
| Build uses the wrong Python / dependency build fails | `.python-version` not read from the service root | Set `PYTHON_VERSION=3.12` (or put `.python-version` in `backend/`). |
| Refreshing a route (e.g. `/admin/students`) returns Netlify **404** | Missing/incorrect SPA fallback, or wrong base dir | Ensure the `/*` → `/index.html` rule is present (it is) and Netlify **Base directory = `frontend`**. |
| Frontend loads but every API call 404s / fails | `netlify.toml` still has the placeholder backend URL, or `/api/*` is below `/*` | Replace `YOUR-BACKEND-URL.example.com` with the real backend origin; keep `/api/*` above the SPA fallback. |
| Emails not sent / AI summary unavailable | Optional `SMTP_*` / `OPENAI_*` env not set | Set those env vars only if you want those features; the app runs fine without them. |
