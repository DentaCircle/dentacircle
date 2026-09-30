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
- **Database:** PostgreSQL in Docker from S0.1. Free locally, removes a migration risk
  later, and it can enforce the appointment overlap rule. The spec's SQLite path is not used.
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

## Open decisions (need the developer's call)

Recommendations are mine, not decisions.

- **Auth approach:** cookie sessions or JWT. Decide in slice S0.4. Recommendation:
  httpOnly cookie session. Keep no token in browser storage.
- **UI component system:** Tailwind alone or a component library. Decide in slice S0.3.
- **Deployment host for the walking skeleton:** decide in slice S0.5, or defer it.
  Synthetic data only, whatever is chosen.
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

Nothing built. Next step: slice S0.1 in ROADMAP.md.
