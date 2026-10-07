# PRODUCT.md

Current scope and decisions. The full idea lives in the original spec
(`Dental_AI_Assistant_Specification.md`, keep a copy in `docs/`). This file is the short,
current version. Update it when scope, decisions, or state change. Do not keep a log here.

## Purpose

An AI-assisted coordination layer for outpatient clinics (dental first). It replaces the
mix of paper, spreadsheets, calls and chat with one workflow: patient, appointment, care,
follow-up, recall, and next appointment. AI comes later. First prove the workflow.

This sits beside the clinic's existing billing tool. It does not replace it. The spec
describes a full clinic platform (billing, a separate medicines module, financial
analytics, a settings screen, a simulated inbox). That is a second product. Do not let a
later slice grow back into a practice-management suite.

Users: clinician, receptionist/coordinator, inventory/admin, clinic admin.

## First useful result (the "core loop")

A coordinator and a clinician can run this end to end with deterministic logic:

1. Book an appointment for a patient.
2. Patient arrives, clinician records a care session, appointment completes.
3. Unfinished care or a clinician-set date creates a follow-up. A recall rule creates a
   recall. Neither: the timeline entry is the only result.
4. When the follow-up is due, the patient appears in the coordinator queue.
5. Coordinator marks the patient contacted and books the next appointment.
6. The patient timeline shows every step.

Later slices extend the same loop with documents, lab work, inventory consumption,
simulated messages, the dashboard and analytics.

## Non-goals

Not now: automated WhatsApp/SMS, voice AI, AI agents, predictive inventory, payment
gateway, insurance and tax workflows, native mobile apps.

Out through M5: billing, invoices, payments and financial analytics, for a single clinic
as much as for many. Revenue reporting stays in the clinic's existing tool.

Outside this project's purpose: diagnosis, treatment recommendation, prescription
automation, full EMR and charting, DICOM/X-ray management.

Also not needed for the MVP: microservices, Kubernetes, multi-region.

## Decisions made

- Modular monolith, monorepo (`apps/api`, `apps/web`). Simple beats scalable until proven otherwise.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic. Frontend: Next.js, TypeScript.
  Chosen by the developer, knowing it is not their strongest stack. Reason: it matches
  the spec and the developer wants to learn it.
- External services sit behind interfaces so they can be swapped.
- AI never controls business truth. See AGENTS.md safety rules.
- Work runs in phases and slices, tracked in ROADMAP.md, with a human review of every diff.
- **Database:** PostgreSQL 16 in Docker from S0.1. Free locally, removes a migration risk
  later, and it can enforce the appointment overlap rule. The spec's SQLite path is not used.
- **Tooling:** Python 3.12, managed with `uv`. API checks are `ruff`, `mypy` (strict) and
  `pytest`. Web checks from S0.1 are TypeScript, ESLint and Vitest, managed with `pnpm`.
  Next.js arrives in S0.3 on top of that package. The database smoke test uses `psycopg`.
- **API database access:** sync SQLAlchemy 2.0 with `psycopg` (decided in S0.2). Routes are
  plain `def`. Async is a later change if ever needed. S0.2 also adds `fastapi`, `uvicorn`,
  `pydantic-settings`, `sqlalchemy`, `alembic` and dev-only `httpx`.
- **Public routes:** `/health`, `/health/ready`, `/auth/login` and `/auth/logout` are open
  without a session. They return no clinic or patient data. Every other route declares
  its roles.
- **Logs and errors:** a 500 logs only the exception class and request id. The full
  traceback is logged only at `LOG_LEVEL=DEBUG` (local, synthetic data). Error bodies and
  logs never echo submitted values.
- **Tenancy:** `clinic_id` on every clinic-owned table from Phase 0. One clinic in the UI,
  no clinic switcher. Cheap now, painful to retrofit.
- **Follow-ups and recalls:** a completed care session does not always create a follow-up.
  Unfinished care or a clinician-set date creates one. A recall rule creates a recall.
  Due and overdue are calculated from the date, never stored. Stored follow-up statuses:
  scheduled, contacted, booked, completed, cancelled.
- **One attention queue.** Incomplete care creates or updates a follow-up rather than
  forming a second list, so one patient cannot appear three times. Recalls stay a separate
  list because they are periodic rather than unfinished work.
- **Appointment statuses:** scheduled, arrived, in progress, completed, cancelled, no-show.
  The spec's Confirmed is dropped until there is a real confirmation step.
- **Audit from the first patient write,** not from the first appointment status change.
  The viewer is the only audit work left for Phase 7.
- **Medicines are ordinary inventory items,** the same engine as gloves and materials, with
  no dose, prescription or diagnosis fields. Care notes stay operational ("what was done,
  what is next"), never clinical findings.
- **Synthetic data only.** M5 is a demo on generated data. No real patient data and no
  production deployment until the DPDP question below is settled.
- **UI:** Tailwind CSS plus shadcn/Radix (decided in S0.3). Component source is copied into
  the repo. S0.3 adds only `button`, `sheet`, `badge` and `card`.
- **Web API client:** response types are generated with `openapi-typescript` from a committed
  OpenAPI snapshot (decided in S0.3). The web app calls the API from the server with
  `API_BASE_URL`. No browser calls and no CORS until S0.4, which chooses CORS or a Next
  rewrite when sessions need it.

- **Auth (decided in S0.4):** an opaque random token in an httpOnly cookie `dc_session`
  (SameSite=Lax, Secure by setting). The database keeps only its SHA-256 hash in
  `auth_session`, so logout and deactivation take effect at once. Not JWT: we load the user
  on every request anyway, and a JWT cannot be revoked or updated without a denylist.
  Passwords are hashed with Argon2id (`argon2-cffi`, the only new dependency in S0.4).
- **Browser access to the API (decided in S0.4, built in S0.5):** a Next rewrite proxies
  `/api/*` to the API, so the browser sees one origin. No CORS. The API keeps its routes
  without a prefix. Check proxy body-size limits at S3.1 (uploads).
- **Roles (decided in S0.4):** four roles (`clinician`, `receptionist`, `inventory_admin`,
  `clinic_admin`) in a `user_role` table, one row per user and role, as text with a check
  constraint, not a PostgreSQL enum. `clinic_admin` has no automatic access: every route
  lists its roles. A test fails on any route that is neither `@public` nor role-protected.
- **Login lookup (decided in S0.4):** email is unique across all clinics. `find_for_login`
  is the only repository query not scoped by `clinic_id`. After login the clinic comes from
  the session, never from the request.
- **Walking skeleton (decided in S0.5):** the one authenticated, clinic-scoped screen is the
  dashboard, showing the signed-in user, roles and clinic from `GET /auth/me`. No new API
  route and no staff list. The page guard runs in the server layout and asks the API whether
  the session is valid (not a Next `proxy.ts` cookie check). Login and logout run in the
  browser through the `/api` rewrite. `/status` is signed-in only.
- **Deployment (deferred in S0.5):** no host chosen. Revisit at the end of Phase 1, when
  there is a demo worth showing. Synthetic data only whatever is chosen. A production web
  build needs `API_BASE_URL` set at build time because the rewrite target is fixed then.
- **Known gaps until real patient data:** CSRF relies on SameSite=Lax with no token or
  Origin check, and there is no login rate limiting. Login and logout are not audited
  until `AuditEvent` exists (S1.1).

- **Clinic day (decided in S1.0):** `clinic` gains `timezone` (IANA, default `Asia/Kolkata`)
  and `default_appointment_minutes` (default 30). Working hours are stored as intervals in
  clinic-local wall time, any number per weekday (0 is Monday). A break is a gap between
  intervals. A day with no interval is closed. The database forbids overlapping or touching
  intervals with an exclusion constraint, so the `btree_gist` extension is enabled here (S1.3
  reuses it). Appointment types have an optional duration that falls back to the clinic
  default, and are deactivated, never deleted. Everyone reads. Only `clinic_admin` writes,
  through the API, with no settings screen. Defaults (Monday to Saturday 09:00 to 18:00, four
  placeholder types) are seeded once by the migration and for new clinics, and live in code.
  Not audited: clinic setup is not on the AGENTS.md audit list.

## Open decisions (need the developer's call)

Recommendations are mine, not decisions.

- **Regulation:** check what India's DPDP Act requires before any real patient data is stored.
- **AI coding tool:** Claude Code, Codex or Cursor. Skills and rules here are plain
  markdown so the choice can change.

## Demo thread

One synthetic story, reused by the M3 core loop check (S2.7) and the seed data (S7.3), so
slices stop inventing their own vocabulary:

1. A consultation is booked and the patient arrives.
2. The clinician records scaling (done, six-month recall) and a root canal planned over
   two visits (first visit done, so a follow-up covers the second).
3. A crown creates lab work. The returned lab result is a document. Lab work marked ready
   creates a follow-up.
4. The coordinator marks the root-canal follow-up contacted and books the next visit.
5. The patient timeline shows those steps in order.

Patient names and details are generated. Never copy a real patient into this thread.

## Stops

Beyond the defaults in AGENTS.md, no extra project stops yet.

## Current state

S0.1 through S0.5 are done. `make dev` starts PostgreSQL, applies migrations, and runs
the API and the web app. Sign in at `/login`. The browser posts through the `/api` rewrite,
so `dc_session` stays on the web origin. The dashboard shows the signed-in user's name,
roles and clinic from `GET /auth/me`. `/` and `/status` require that session. Create a
user with `make create-user`. Deployment is still deferred to the end of Phase 1.
Next slice: S1.0 clinic day is built and waiting for review.
