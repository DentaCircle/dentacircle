# PRODUCT.md

Current scope and decisions. The full idea lives in the original spec
(`Dental_AI_Assistant_Specification.md`, keep a copy in `docs/`). This file is the short,
current version. Update it when scope, decisions, or state change. Do not keep a log here.

## Purpose

An AI-assisted operating layer for outpatient clinics (dental first). It replaces the mix
of paper, spreadsheets, calls and chat with one workflow: patient, appointment, care,
follow-up, recall, and next appointment. AI comes later. First prove the workflow.

Users: clinician, receptionist/coordinator, inventory/admin, clinic admin.

## First useful result (the "core loop")

A coordinator and a clinician can run this end to end with deterministic logic:

1. Book an appointment for a patient.
2. Patient arrives, clinician records a care session, appointment completes.
3. A follow-up is created, with a recall date where applicable.
4. When the follow-up is due, the patient appears in the coordinator queue.
5. Coordinator marks the patient contacted and books the next appointment.
6. The patient timeline shows every step.

Later slices extend the same loop with documents, lab work, inventory consumption,
simulated messages, the dashboard and analytics.

## Non-goals

Not now: automated WhatsApp/SMS, voice AI, AI agents, predictive inventory, payment
gateway, insurance and tax workflows, native mobile apps, multi-clinic billing.

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

## Open decisions (need the developer's call)

Recommendations are mine, not decisions.

- **Database:** SQLite (as in the spec) or PostgreSQL in Docker from day one.
  Recommendation: PostgreSQL from day one. It is free locally, removes a migration risk
  later, and SQLite behaves differently on types, constraints and concurrency.
- **Tenancy:** `clinic_id` on every clinic-owned table from Phase 0. Recommendation: yes.
  Cheap now, painful to retrofit.
- **Auth approach:** cookie sessions or JWT. Decide in slice S0.4.
- **UI component system:** Tailwind alone or a component library. Decide in slice S0.3.
- **Deployment host for the walking skeleton:** decide in slice S0.5, or defer it.
- **Regulation:** check what India's DPDP Act requires before any real patient data is stored.
  The MVP uses synthetic data only until this is settled.
- **AI coding tool:** Claude Code, Codex or Cursor. Skills and rules here are plain
  markdown so the choice can change.

## Stops

Beyond the defaults in AGENTS.md, no extra project stops yet.

## Current state

Nothing built. Next step: slice S0.1 in ROADMAP.md.
