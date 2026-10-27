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

- **Patient timeline (decided in S2.6):** each step writes one `timeline_event` in the same
  transaction as the change. The row stores a closed `kind`, the actor, the time and at most
  one subject id. It stores no names, dates, notes or other patient values. Audit stays as
  decided in S1.2 (no values and no direction of a status change). There is no backfill.
  `clinician`, `receptionist` and `clinic_admin` read `GET /patients/{id}/timeline`, newest
  first. Subject details are read live, so a renamed item shows its current name.

- **Core loop check (decided in S2.7):** the M3 loop is proven by an API-level test through
  the HTTP routes plus a written click-through in `docs/demo-m3.md`. No browser automation
  (Playwright or similar) until a slice of its own, because it adds a dependency and a CI
  service. Lab work, the crown and the document in the Demo thread arrive with S3.x; M3 uses
  the Scaling and root canal story from the S2.7 brief.
- **Appointment client maintenance (decided in S2.8):** appointment availability keeps runtime
  response validation behind a feature-local lifecycle that cancels superseded requests and
  rejects stale results. Booking and rescheduling share timeout transport and distinguish a
  patient scheduling conflict from a clinician slot conflict with fixed safe copy.
- **Document upload (decided in S3.1):** a file is sent as the raw request body with the name
  in the `X-Document-Filename` header, not multipart, so no `python-multipart` dependency and
  access logs do not carry the name in the URL. Allowed types are
  PDF, PNG and JPEG, decided from the first bytes of the file, up to 8 MiB counted while the
  body is read (under Next's 10 MB proxy default). Files sit behind a `DocumentStorage`
  interface in `integrations/storage/`; the only real adapter writes to local disk under
  `STORAGE_ROOT`, with a server-built key `{clinic_id}/{document_id}`. The file is stored
  first, then the row and audit event are committed, and the file is deleted if that fails.
  `receptionist`, `clinician` and `clinic_admin` upload, list and download; `inventory_admin`
  may not. Inactive patients get no new uploads but their documents stay readable. Downloads
  use `nosniff` and default to attachment; inline viewing and links are S3.2. Filenames never
  go into audit rows, logs, error bodies or storage keys. No delete, no document type, date or
  description at upload.
- **Document viewer and links (decided in S3.2):** `GET .../file` takes optional
  `disposition=inline` or `attachment` (default attachment). Inline images use
  `Content-Security-Policy: sandbox; default-src 'none'` on the response; inline PDFs do not,
  because Chrome's PDF viewer breaks under that CSP, so PDFs open in a new tab from the viewer
  page with `inline` and `nosniff` only. `GET .../documents/{id}` returns one item. Optional
  nullable `appointment_id` and `follow_up_id` on the document row link to the same patient in
  the clinic; set or clear with `PATCH`, or at upload via query parameters. Wrong patient or
  clinic is 404. Link changes refuse an inactive patient (409). Filter the list by visit or
  follow-up id. Linking in the UI starts from the calendar visit row or the follow-up queue
  (filtered documents page, upload with context, link or unlink existing files). No visit or
  follow-up pickers from the unfiltered documents page alone. Timeline kind `document_uploaded`
  with `document_id`; migration `0016` adds the column and recreates the timeline check
  constraints. Upload writes the timeline row in the same transaction as the document row; link
  changes do not. No backfill for S3.1 uploads. The timeline response includes the current
  filename read live. Link updates write `document` `update` audit with field names only.
- **Lab work (decided in S3.3):** external lab work is tracked per patient, with statuses that
  follow the patient, not the clinic-to-lab hand-off: `pending` (requested, not back),
  `ready` (back at the clinic, waiting for the patient), `collected` (the patient took it),
  `cancelled`. Moves: `pending` to `ready` or `cancelled`, `ready` to `collected` or
  `cancelled`. No skipping, `collected` and `cancelled` are final, no undo. A title (up to 200
  characters) and optional expected date and related visit; no notes, lab name or cost.
  `clinician`, `receptionist` and `clinic_admin` read and write; `inventory_admin` may not.
  New work is refused for an inactive patient, but its open work can still move. `overdue` is
  calculated (a `pending` item past its expected date), never stored. Marking `ready` for an
  active patient creates an open follow-up due today with no visit, or pulls a `scheduled` or
  `contacted` follow-up forward to today and keeps its status. A `booked` follow-up is left
  alone. Collecting or cancelling touches no follow-up, and the coordinator closes it.
  Documents link to one lab item (nullable `document.lab_work_id`, same rules as the visit and
  follow-up links; linking starts from the lab row). Lab timeline kinds `lab_work_created`,
  `lab_work_ready`, `lab_work_collected` and `lab_work_cancelled` need migration `0017` to
  recreate the timeline check constraints, approved here. Audit rows list field names only.
- **Inventory items (decided in S4.1):** categories, items and batches are three new tables
  (migration `0018`, additive). Quantities are whole numbers, so a smaller unit stands in for
  fractions. A batch is a number plus an optional expiry date and holds no quantity. Stock
  arrives only through S4.2 transactions, never as a typed or overwritten number. One
  `low_stock_threshold` per item, no reorder threshold. Categories are a per-clinic table with
  create and rename, no delete and no seeded defaults. Items are deactivated, never deleted.
  Names are unique per clinic ignoring case, and batch numbers unique per item. `inventory_admin`
  and `clinic_admin` write. They, plus `clinician`, read. `receptionist` has no access.
  Supplier and purchase cost are left out (billing and financial analytics are out through M5);
  confirm again at S4.2. `expired` is calculated from the clinic-local date. The expiring-soon
  window belongs to S4.4. Audit rows list field names only. S4.1 stays one slice, reviewed in
  six pieces.
- **Stock and transactions (decided in S4.2):** stock is never stored or typed in. It is the sum
  of an append-only `inventory_transaction` table (migration `0019`, additive), per batch, and
  per item as the sum over its batches. A transaction has a batch (the item is reached through
  it), a type, an optional reason, a whole-number signed change, the actor and the time. It has
  no note, cost or supplier; the S4.1 question is settled and both stay out through M5. Types:
  `restock` (positive, into an existing batch) and `adjustment` with reason `damaged`,
  `expired` (both negative) or `correction` (either sign). Procedure consumption is S4.3.
  Stock cannot go below 0 (409 `insufficient_stock`), checked under a lock on the batch row.
  Restock is refused for an inactive item; adjustments are allowed so old stock can be written
  off. A trigger makes the database refuse `UPDATE` and `DELETE` on the table (the first trigger
  in the repo), and a mistake is fixed with a `correction`. `inventory_admin` and `clinic_admin`
  write; they plus `clinician` read stock and history; `receptionist` has no access. Expired
  batches still count in stock until S4.4 decides alert treatment. Audit rows list no
  quantities.
- **Procedure resource rules (decided in S4.3):** a rule says an appointment type uses N whole
  units of an inventory item (`procedure_resource_rule`, one per type and item, 1 to 1,000).
  Rules are keyed by appointment type, not care item, because care items are free text with no
  catalog. Completing a visit writes `consumption` transactions in the same transaction,
  negative, linked to the visit by a new nullable `inventory_transaction.appointment_id`
  (migration `0020`, changes an existing table, approved here). Batches are taken earliest
  expiry first, skipping expired batches and inactive items. Short stock takes what exists and
  never blocks the visit; the shortfall is not recorded (S4.4 alerts on stock at 0). A care
  session consumes nothing. `inventory_admin` and `clinic_admin` write rules; they plus
  `clinician` read; `receptionist` has no access. Rule changes are audited with field names
  only, and rule delete is a real delete.

## Open decisions (need the developer's call)

Recommendations are mine, not decisions.

- **Regulation:** check what India's DPDP Act requires before any real patient data is stored.
- **AI coding tool:** Claude Code, Codex or Cursor. Skills and rules here are plain
  markdown so the choice can change.

## Demo thread

One synthetic story, reused by the M3 core loop check (S2.7) and the seed data (S7.3), so
slices stop inventing their own vocabulary:

Step 3 (crown, lab, document) needs S3.x. The M3 check in S2.7 runs steps 1, 2, 4 and 5
with a Scaling visit and a root canal item.

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

Staff with `clinician`, `receptionist` or `clinic_admin` can open `/patients/[id]/timeline`
for one patient. Each registration, visit step, care item step, care session, follow-up step
and recall step writes a `timeline_event` in the same transaction (migration `0014`). The
list is newest first, grouped by clinic-local day on the web. Visit and care rows link to the
calendar day or care page. Reading it writes no audit row. History from before this slice is
not backfilled, so an existing patient starts empty. `inventory_admin` is refused.

The M3 core loop in PRODUCT.md is checked by `apps/api/tests/test_core_loop.py` through the
HTTP routes: follow-up and recall paths, Due and All open queue views, clinician-set due
today, the neither outcome, cancel of a booked follow-up visit, the full timeline kind
sequence, and role plus tenancy guards. `docs/demo-m3.md` is the browser walk-through for
the same story (linked from README). This slice added no new routes or UI.

Staff with `clinician`, `receptionist` or `clinic_admin` can open `/patients/[id]/documents`,
upload a PDF, PNG or JPEG up to 8 MiB, see a newest-first list, open a file in the viewer
(`/patients/[id]/documents/[documentId]`), and download it as an attachment or inline (images
in-page; PDF via "Open in new tab", no iframe). Files sit behind a `DocumentStorage` interface;
the local adapter writes under `STORAGE_ROOT` (migration `0015`). A document may link to one
visit and one follow-up for the same patient (migration `0016`); calendar and follow-up queue
rows link to a filtered documents page where staff upload with context, link existing files,
or unlink. Link changes write a `document` update audit with field names only; inactive patients
cannot change links. A successful upload writes one `document` create audit event and a
`document_uploaded` timeline row in the same transaction as the row, without the filename in
audit. Inactive patients cannot upload; existing files stay readable. `inventory_admin` is
refused. A document may also link to one lab item for the same patient; staff set or clear that
link at upload, from a lab-filtered documents page, or with `PATCH`. Link changes write a
`document` update audit with field names only. There is no delete or rename yet.

The same three roles can record external lab work per patient on `/patients/[id]/lab` and on
the clinic `/lab` list (Open and All). Statuses are pending, ready, collected and cancelled,
with the moves in PRODUCT decisions above. Marking ready for an active patient creates or pulls
forward an open follow-up due today. Each row links to documents filtered by that lab item.
Lab rows show on the patient timeline. Status moves and creates write `lab_work` audit events
and the four lab timeline kinds in the same transaction as the row (migration `0017`).
`inventory_admin` is refused. New lab work is refused for an inactive patient; existing items
can still move and list.

`inventory_admin` and `clinic_admin` can set up categories, items and batches on `/inventory`
and `/inventory/[id]`, restock a batch, and adjust stock with a reason (`damaged`, `expired`,
or `correction`). Stock is never typed in or stored; it is the sum of an append-only
`inventory_transaction` table per batch and per item (migration `0019`). Restock on an inactive
item is refused; adjustments are still allowed. The service locks the batch row and refuses
a change that would go below zero. Each transaction writes one `inventory_transaction` create
audit event in the same transaction. The item page shows calculated stock, batch quantities,
and a paginated history; the list shows a Stock column. A clinician can read stock and history
and cannot use the forms. A receptionist is refused. A batch is a number plus an optional expiry;
`expired` is calculated from the clinic-local date and is not stored. Expired batches still
count in stock until S4.4. Items are deactivated, never deleted. Item and batch setup writes
audit events with field names only (migration `0018`).

`inventory_admin` and `clinic_admin` can set visit-type rules on
`/inventory/rules`: each rule names one active item and a whole quantity from 1 to 1,000
for an appointment type (`procedure_resource_rule`, migration `0020`). They and
`clinician` can list rules; `receptionist` is refused. When a visit moves to `completed`,
the API writes `consumption` transactions in the same transaction as the status change,
linked by `inventory_transaction.appointment_id`, taking earliest unexpired batch stock
first and never blocking completion on short stock. Item history shows "Used in visit"
with a link to that visit's calendar day. Rule writes and each consumption write audit
events with field names only. A care session does not consume stock. Low-stock and
expiring alerts are not in yet (S4.4).
