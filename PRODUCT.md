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
  Unfinished care or a clinician-set date creates one. A recall rule on the appointment
  type creates a recall. Due and overdue are calculated from the date, never stored.
  Stored follow-up and recall statuses: scheduled, contacted, booked, completed, cancelled.
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
  Origin check, and there is no login rate limiting. Login and logout stay unaudited.
  S1.1 records patient registration only.

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

- **Patients (decided in S1.1):** staff register patients. There is no patient self-registration
  or self-booking. The patient ID is a number per clinic, shown as `P-0001`, allocated from a
  `patient_number_counter` row so concurrent creates cannot collide. Required fields are name
  and phone, and date of birth is optional. Phone is stored as entered and as digits only, for
  search. Duplicate names and phones are allowed. `receptionist`, `clinician` and
  `clinic_admin` may register and list patients, and `inventory_admin` may not. Search is plain
  "contains" with no `pg_trgm`. Add a trigram index only if search gets slow.
- **Audit (decided in S1.1):** one `audit_event` table holds who, what entity, which action and
  when. It never stores patient values. Update events (from S1.2) list changed field names
  only. The service writes the event in the same transaction as the change, through one
  `audit_service.record` call, not a trigger. There is no update or delete path for audit rows.

- **Patient status (decided in S1.2):** a patient is `active` or `inactive`, stored on
  `patient.status` (default `active`). Patients are never deleted, so inactive is how staff
  retire a record while keeping history. `receptionist`, `clinician` and `clinic_admin` may
  change it. The list shows all patients by default, with a `status` filter. Edits are last
  write wins, with no version check. Update and status-change audit events record changed
  field names only in `audit_event.changed_fields`, never values and never the direction of a
  status change. Rules that use status (for example no booking for an inactive patient) come
  with the slice that needs them.

- **Appointments (decided in S1.3):** start times sit on a 15-minute grid counted from each
  working-hours interval's opening time. The grid only sets where an appointment may start.
  Its length comes from the appointment type, or the clinic default, with no per-booking
  override, and the whole span must fit inside one interval. Back-to-back is allowed (one ends
  10:30, the next may start 10:30). A PostgreSQL exclusion constraint forbids overlapping
  appointments for one clinician; `cancelled` and `no_show` do not block. One patient in two
  overlapping blocking appointments is refused by migration `0007` (gist exclusion, same
  rules as the clinician constraint). Inactive patients cannot be
  booked. Bookings may be up to 365 days ahead, as a guard against typos. API times are sent in
  the clinic's offset. `receptionist`, `clinician` and `clinic_admin` book, and
  `inventory_admin` does not. `GET /clinicians` lists only id and name of active users holding
  `clinician`. No appointment notes yet. Booking writes an `appointment` `create` audit event.

- **Calendar (decided in S1.4):** the desk sees an agenda list for one day or a Monday–Sunday
  week, not a time grid. A list covers at most seven clinic-local days. Cancelled visits are
  hidden; no-show stays visible. Only a `scheduled` visit can be cancelled or moved, and there
  is no cancel reason. Reschedule keeps the patient, the type and the original length, and may
  change the start and the clinician. The same row is updated. The calendar response includes
  the patient name for the three roles that can already list patients.

- **Appointment status (decided in S1.5):** a visit moves only `scheduled` to `arrived` or
  `no_show`, then `arrived` to `in_progress`, then `in_progress` to `completed`. There is no
  undo. `receptionist`, `clinician` and `clinic_admin` may mark arrived and no-show. Only
  `clinician` and `clinic_admin` may start or complete. Arrived is only on the clinic-local
  day of the visit. No-show is only at or after the start. One route,
  `POST /appointments/{id}/status`, writes one `status_change` audit row. Cancel stays on
  `/cancel` and still applies to `scheduled` only.

- **Care plan and items (decided in S2.1a):** S2.1 is split into S2.1a (plan and items) and
  S2.1b (care sessions). A patient has care plans, a plan has care items, and an item is a
  free-text service name (up to 200 characters) with no notes, tooth, cost or catalog. Item
  statuses are `planned`, `started`, `completed`, `cancelled`. Allowed moves: `planned` to
  any of the other three, `started` to `completed` or `cancelled`. Completed and cancelled
  are final, with no undo. A plan has no stored status: it is open while any item is planned
  or started. `clinician` and `clinic_admin` write. `receptionist` may read, because the
  coordinator queue needs unfinished care. `inventory_admin` has no access. No new care for
  an inactive patient, but its open items can still be renamed, finished or cancelled. One
  status method serves the manual route now and the care session in S2.1b. Audit rows use
  entity types `care_plan` and `care_item` and list field names only, never titles or names.

- **Care sessions (decided in S2.1b):** one session per visit, saved in one step. No edit, no
  second session, no notes and no prescription. It lists care items marked `started` or
  `completed` on an `arrived` or `in_progress` visit, and those items move through the S2.1a
  rules in the same step. Saving a session does not complete the visit. A missed item is
  updated on the care page, and that later change is not added to the session. Any
  `clinician` or `clinic_admin` may record; `receptionist` may read. For S2.2 and S2.3,
  "session completion" means the visit is completed. Migration `0009` adds unique
  `(id, clinic_id)` on `appointment` and `care_item` so a session cannot point at another
  clinic's visit or item.

- **Incomplete care (decided in S2.2):** S2.2 owns the `follow_up` table. A follow-up is
  written when a visit moves to `completed` and the patient is active with a `planned` or
  `started` item on any plan, whether or not that visit has a care session. `due_on` is the
  clinic-local completion date plus 7 days, unless the clinician sets a date (S2.3). An
  existing open follow-up keeps its status. Without a clinician date, only `appointment_id`
  moves to the visit just completed. An inactive patient still completes, and no follow-up
  is written. A follow-up stays open when the care is later finished, until a coordinator
  closes it.

- **Manual follow-up and clinician date (decided in S2.3):** `follow_up.appointment_id` is
  nullable so a follow-up can exist with no visit. `clinician`, `receptionist` and
  `clinic_admin` may `POST /patients/{id}/follow-up` with `{due_on}` for an active patient
  who has no open follow-up. `due_on` is the clinic-local day of the request through 365
  days ahead. A second open follow-up is refused. On `POST /appointments/{id}/status` with
  `status: completed`, an optional `follow_up_due_on` creates or updates the open follow-up
  to that date and links it to the visit, even when no care item is open. The date replaces
  an existing open follow-up's date; its status stays. The same date window applies. An
  inactive patient still completes and the date is dropped. Without the date, S2.2 is
  unchanged.

- **Coordinator queue (decided in S2.4):** `GET /follow-ups` lists open follow-ups with a
  calculated `timing` (`overdue`, `due_today`, `upcoming`) from the clinic-local date. The Due
  view is `scheduled` and `contacted` rows due today or earlier. All open also shows `booked`
  and future rows. Follow-ups of inactive patients are hidden. `clinician`, `receptionist` and
  `clinic_admin` may list, mark contacted (`scheduled` to `contacted`, no undo) and book.
  Booking from the queue reuses `book_appointment`, may start from `scheduled` or `contacted`,
  and in one transaction sets `booked` and stores `booked_appointment_id` (additive migration
  `0012`, composite clinic FK). Closing a follow-up is S2.4b.

- **Closing follow-ups (decided in S2.4b):** completing the visit stored in
  `booked_appointment_id` of a `booked` follow-up sets it to `completed`, before S2.2 runs,
  so S2.2 and S2.3 can then create a new follow-up. This happens even for an inactive
  patient. Cancelling or no-show on that visit releases the follow-up to `contacted`
  (`due_on` and `booked_appointment_id` kept), so the patient returns to the Due view.
  Reschedule changes nothing. `POST /follow-ups/{id}/cancel` (204, no body, no reason, no
  undo) works from `scheduled`, `contacted` or `booked`, for the same three roles, and
  leaves a booked visit on the calendar. Finishing care never closes a follow-up by itself;
  the coordinator cancels it. No migration.

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

S0.1 through S1.4 are done. `make dev` starts PostgreSQL, applies migrations, and runs
the API and the web app. Sign in at `/login`. The browser posts through the `/api` rewrite,
so `dc_session` stays on the web origin. The dashboard shows the signed-in user's name,
roles and clinic from `GET /auth/me`. `/` and `/status` require that session. Create a
user with `make create-user`. Deployment is still deferred to the end of Phase 1.

Each clinic has a timezone, weekly working hours, a default appointment duration and
appointment types in the database. Everyone signed in can read them with `GET /clinic/day`
and `GET /appointment-types`. Only `clinic_admin` can change them through the API. There is
no settings screen yet; README has curl examples. Migration `0003` enables `btree_gist` for
working-hours overlap; migrations `0006` and `0007` use it for clinician and patient
appointment overlap. New clinics are seeded once; existing clinics were backfilled by the
migration.

Staff with `receptionist`, `clinician` or `clinic_admin` can register patients, open a
patient from the list, edit name, phone and date of birth, and set `active` or `inactive`.
The API exposes `GET`, `PATCH` and `PUT /patients/{id}/status` plus `status` on list search.
The web has `/patients/[id]` and `/patients/[id]/edit`; edits and status changes go through
the `/api` rewrite. Patient numbers are per clinic (`P-0001`, …). Migrations `0004` and `0005`
add patients, audit events, `patient.status` and `audit_event.changed_fields`. Registration,
updates and status changes write audit rows (field names only, no patient values). Login and
logout are still not audited.

The same three roles can book appointments for active patients: `GET /clinicians`,
`GET /appointments/availability`, `POST /appointments`, and `GET /patients/{id}/appointments`.
Slots follow clinic hours on a 15-minute grid; the database refuses overlapping visits for one
clinician. The web book flow is `/patients/[id]/book`; the patient page shows upcoming visits
and a book link when allowed. A successful booking writes an `appointment` create audit event.

The same three roles can open `/calendar` for a day or a Monday–Sunday week (agenda list, up
to seven clinic-local days), filter by clinician, cancel a `scheduled` visit, and reschedule
one (keeping patient, type and length). `GET /appointments` lists visits in a range;
`GET /appointments/{id}`, `POST .../cancel` and `POST .../reschedule` return the same item
shape. Cancelled visits are hidden on the list; reschedule availability can use the visit id
so the visit's own span does not block. Cancel and reschedule write audit rows in the same
transaction. A time-only reschedule may keep an inactive assigned clinician; choosing another
clinician still requires an active one.

The same three roles can mark a visit arrived or no-show from the calendar; only a clinician or
clinic_admin can start or complete it. Arrived is allowed only on the visit's clinic-local day;
no-show only at or after the start. `POST /appointments/{id}/status` applies one allowed move,
locks the row, and writes a `status_change` audit event in the same transaction. No-show frees
the slot for booking; arrived, in progress and completed keep it blocked. Cancel stays on
`/cancel` for scheduled visits only.

A patient can have care plans; each plan has care items with a free-text service name and a
status of planned, started, completed or cancelled. `clinician` and `clinic_admin` create plans
and items, rename them, and move items through the allowed transitions with
`POST /care-items/{id}/status`. `receptionist` can read plans on `GET /patients/{id}/care-plans`
and on `/patients/[id]/care`. `inventory_admin` gets 403. New plans and items are refused for
an inactive patient; existing items can still be finished. Migration `0008` adds `care_plan` and
`care_item`. Open versus finished on a plan is computed from its items. There is no undo for
care item status. The web care page does not rename plan titles yet, though the API can.

A clinician or clinic admin can record one care session on an arrived or in-progress visit
from the calendar. The session lists the items marked started or completed, and those items
move through the same status rules. Reception can read the session. Saving it does not
complete the visit, and a missed item stays on the care page rather than being added later.
Migration `0009` adds `care_session` and `care_session_item`, plus unique `(id, clinic_id)`
on `appointment` and `care_item`. Completing a visit is separate from saving a care session.

When a visit moves to `completed` and the patient is active with a planned or started item on
any plan, the API creates or updates one open follow-up in the same transaction: status
`scheduled`, `due_on` seven clinic-local days after completion, `appointment_id` on the visit
just completed. An existing open follow-up keeps its status and due date; only the visit link
moves. `GET /patients/{id}/follow-up` returns the open row or null for clinician, receptionist
and clinic_admin. `/patients/[id]/care` shows the due date and badge above the plans.
`inventory_admin` still gets 403. Migration `0010` adds `follow_up`. Finishing the last care
item does not close the follow-up.

Clinician, receptionist, and clinic admin can create a follow-up by hand on Care when the
patient is active and has no open follow-up. The date is today through 365 days, clinic-local,
and the row has no visit. On the calendar, confirming Complete can set that date. The date
creates a follow-up even when every care item is finished, and it replaces the date on an
existing open follow-up. Migration `0011` allows a null visit. Without a date, completion
still uses the seven-day rule from S2.2.

Clinician, receptionist, and clinic admin can open `/follow-ups` for the coordinator queue.
Due (default) lists scheduled and contacted rows due today or earlier, with timing calculated
from the clinic-local date. All open also shows booked and future rows. Inactive patients are
hidden. Mark contacted moves scheduled to contacted. Book visit reuses the patient booking
screen and `POST /follow-ups/{id}/book`, which creates the appointment, sets booked, and
stores `booked_appointment_id` in one transaction (migration `0012`). `inventory_admin` is
refused.

Completing the visit stored in `booked_appointment_id` closes that `booked` follow-up to
`completed` in the same transaction, before S2.2 can write a new open row. Cancelling or
no-show on that visit releases the follow-up to `contacted` with `due_on` and
`booked_appointment_id` kept, so Due can show the patient again. Reschedule leaves the row
booked. `POST /follow-ups/{id}/cancel` (204, no body) closes any open follow-up from the
queue for the same three roles; a booked visit stays on the calendar. Each row on
`/follow-ups` has Cancel follow-up with a confirmation. Finishing care still does not close
a follow-up by itself.

A recall rule lives on the appointment type: empty, or a whole number of months from 1 to 60.
New clinics get Scaling at 6 months, and migration `0013` fills that only
where an existing Scaling rule is empty. Completing a visit of a rule-enabled type writes
one open recall for an active patient, dated that many clinic-local months ahead. A later
rule-enabled visit replaces a scheduled or contacted recall and keeps its status. A booked
recall stays until that visit is completed, cancelled, a no-show, or the coordinator cancels
it. Clinician, receptionist, and clinic admin can open `/recalls`. Due lists scheduled and
contacted rows due today or earlier. All open also shows booked and future rows. The same
three roles can mark contacted, book the next visit, and cancel. Completing the booked visit
closes the recall before a new one can be written. Cancelling or no-show on that visit
returns it to contacted. Recalls stay off the follow-up queue.

Next slice: S2.6 patient timeline — one chronological view of the steps above.
