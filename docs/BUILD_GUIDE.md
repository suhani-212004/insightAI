# Build Guide — from scratch to finished project

This is the order the project was built in. Each phase lists what to build, which files hold it,
and how to check it works before moving on. If you are rebuilding it yourself, follow the same order.

---

## Phase 0 — Set up the skeleton (day 1)

1. Create the folders: `backend/`, `frontend/`, `docker/`, `docs/`, `sample_data/`.
2. `docker-compose.yml` with `db` (Postgres 16) and `redis` first, so you have databases on day 1.
3. `docker/postgres/init.sql`: two roles — `insight` (the app) and `insight_readonly` (only for
   running AI SQL later) — plus `insight` and `insight_test` databases.
4. Backend: `python -m venv .venv`, `pip install -r requirements.txt`, then
   `app/core/config.py` (settings from `.env`), `app/core/database.py` (two engines), `app/main.py`.
5. Frontend: `npx create-next-app` (TypeScript, Tailwind, App Router) or copy `package.json` here.

**Check:** `uvicorn app.main:app --reload` → `GET /health` returns `{"status": "ok"}`.

## Phase 1 — Auth, organisations, roles (week 1)

| Build | File |
|---|---|
| Models: `Organization`, `User`, `Membership(role)` | `app/models/__init__.py` |
| bcrypt hashing + JWT create/decode | `app/core/security.py` |
| `get_current_user`, `require_role("admin")`, `TenantContext` | `app/api/deps.py` |
| Signup (creates user + org + owner membership + `org_<id>` schema), login, me | `app/api/v1/auth.py`, `services/orgs.py`, `services/tenancy.py` |
| Members: list, invite, change role, remove (last-owner protection) | `app/api/v1/orgs.py` |
| Frontend auth context (token in localStorage, current org), login/signup pages | `src/lib/auth.tsx`, `src/lib/api.ts`, `src/app/login`, `src/app/signup` |

**Check:** `tests/test_auth_rbac.py` — viewer can't upload (403), another org's id returns 404.

## Phase 2 — Data ingestion (week 2)

1. `services/ingestion.py`
   - `slugify` column names (`"Order Date ($)"` → `order_date`), de-duplicate them.
   - `clean_frame`: turn `"1,200"` into numbers and date-looking columns into timestamps.
   - `ingest_frame`: `df.to_sql()` into `org_<id>.<table>`, decimals as `NUMERIC`, grant SELECT to
     the read-only role, store column types + row count on the `Dataset` row.
2. `POST /datasets/upload` (multipart), list, preview, delete — `api/v1/datasets.py`.
3. Connectors — `services/connectors.py`, `api/v1/connectors.py`:
   - **Webhook**: public `POST /ingest/webhook/{id}/{secret}`; rows are appended.
   - **API polling**: store URL + interval + JSON path; worker fetches with `httpx` and replaces the table.
4. Real-time: `services/events.py` publishes to Redis; `GET /stream` (SSE) relays to the browser;
   `src/lib/useEvents.ts` shows toasts and refreshes pages.
5. Frontend: `src/app/(app)/datasets/` — upload button, dataset cards, connector modal, preview table.

**Check:** `tests/test_datasets.py`, `tests/test_billing_connectors.py::test_webhook_connector_ingests_and_appends`.

## Phase 3 — Charts and dashboards (weeks 3–4)

1. `Dashboard(layout JSON)` and `Widget(sql, chart JSON)` models; CRUD + `PUT /dashboards/{id}/layout`
   + `GET /widgets/{id}/data` — `api/v1/dashboards.py`.
2. `src/components/charts/ChartRenderer.tsx`: one component for all types.
   Recharts for line / bar / pie / scatter; `Heatmap.tsx` (CSS grid) and `FunnelBars.tsx` because
   Recharts' versions are weak; `DataTable.tsx` as fallback.
3. `src/lib/chartData.ts`: number formatting, axis fallback, heatmap matrix, CSV export (unit tested).
4. `src/components/WidgetEditor.tsx`: write SQL → Run → preview → choose chart + axes → Save.
5. `src/app/(app)/dashboards/[id]/page.tsx`: `react-grid-layout` with a drag handle; layout changes
   are debounced and saved to the API.

**Check:** `tests/test_dashboards.py`, `src/__tests__/ChartRenderer.test.tsx`.

## Phase 4 — Safe SQL execution (week 5, before any AI!)

Do this *before* connecting the LLM.

1. `services/sql_guard.py` — parse with `sqlglot`; allow only SELECT/UNION/CTE; reject write/DDL nodes,
   foreign schemas, unknown tables and dangerous functions.
2. `services/query_runner.py` — read-only transaction, `search_path` = tenant schema, timeout, row limit,
   run on the read-only DB role, JSON-safe values.

**Check:** `tests/test_sql_guard.py` (25 attack/allow cases) and
`test_readonly_role_cannot_read_app_tables_or_write`.

## Phase 5 — AI query engine (week 5–6)

1. `services/ai_query.py`
   - `describe_schema()`: tables, column types, 3 sample rows each.
   - `SYSTEM_PROMPT`: rules for SQL + how to pick a chart type.
   - `OpenAIGenerator`: `ChatOpenAI(...).with_structured_output(AIAnswer)` → `{sql, chart, explanation}`.
   - `ask()`: load the last 10 turns as memory → generate → validate + run → on error, send the error back
     once → save messages.
   - `_infer_chart()`: repairs axis names the LLM got wrong so the frontend always renders.
2. `api/v1/ai.py` — ask, list sessions, read a session.
3. `src/app/(app)/chat/page.tsx` — conversation list, suggested questions, chart answers,
   Show SQL, CSV download, **Pin to dashboard**.
4. `services/anomaly.py` — z-score (>3σ) + IQR (3×) per numeric column; runs after upload and hourly.

**Check:** `tests/test_ai.py` uses a fake generator to test memory, retries, unsafe SQL, quotas.

## Phase 6 — Billing and feature gates (week 6)

1. `services/plans.py` — the plan table, `check_limit()`, `require_feature()`, daily AI quota.
2. `services/billing.py` — Stripe Checkout, Customer Portal, webhook → plan mapping.
3. `api/v1/billing.py` — `/billing`, `/checkout`, `/portal`, `/webhook`, plus `/dev/set-plan` for demos
   (disabled when `ENV=prod`).
4. `src/app/(app)/settings/page.tsx` — plan cards, usage, members table.

**Check:** `tests/test_billing_connectors.py::test_stripe_events_update_plan`; then real test mode with
`stripe listen` and card 4242 4242 4242 4242.

## Phase 7 — Reports, worker, polish (week 7)

1. `services/reports.py` + `src/app/print/dashboards/[id]/page.tsx` — Playwright PDF export.
2. `app/workers/tasks.py` — ARQ cron: poll connectors (every minute), rescan anomalies (hourly),
   scheduled reports (07:00).
3. `app/seed.py` + `sample_data/` — 2 demo orgs (Pro and Free), users for each role, a 6-widget dashboard
   that shows every chart type, planted anomalies.
4. Loading/empty/error states, dark mode, mobile layout.

## Phase 8 — Ship it (week 8)

1. Tests: `pytest` (target > 75%; currently 88%) and `npm test`.
2. CI: `.github/workflows/ci.yml` fails the build under 75% coverage.
3. Deploy (see README §6), then seed the production demo orgs.
4. Architecture diagram: `docs/ARCHITECTURE.md` (Mermaid renders on GitHub).
5. Demo video (about 8 minutes) — suggested script:
   - 0:00 Problem + architecture diagram
   - 1:00 Sign up, upload a CSV, live toast via SSE
   - 2:00 Build a dashboard: add widgets, drag/resize, all 6 chart types
   - 3:30 Ask AI: question → chart, follow-up that uses memory, Show SQL, pin to dashboard
   - 5:00 Safety: ask it to "delete all data" and show it's blocked; switch org to show isolation
   - 5:45 Roles: log in as Viewer, show restricted UI
   - 6:15 Billing: hit a Free limit (402), upgrade via Stripe test checkout, feature unlocks
   - 7:15 Anomalies + PDF export
   - 7:45 Tests/coverage + wrap-up

## Ideas for extra credit

- Alembic migrations instead of `create_all`.
- Refresh tokens / httpOnly cookies instead of localStorage.
- Email invites (Resend/SES) instead of temporary passwords.
- Postgres row-level security as a fourth safety layer.
- Cache widget results in Redis; invalidate on `dataset.updated`.
- Rate limiting on `/ai/ask` and `/auth/login`.
