# ROADMAP.md

The tracker. Phases are made of slices. A slice is one reviewable change, about half a day
to a day of work, with a visible result. Tick a slice only after `/ship-seal`.

**Now:** S0.4 (not started)

Milestones are demoable. Each one is a real stopping point.

- **M1 Walking skeleton:** login works, one clinic-scoped screen reads real data, CI is green.
- **M2 Front desk:** patients and appointments are usable day to day.
- **M3 Core loop:** the loop in PRODUCT.md works end to end. This is the first real demo.
- **M4 Connected clinic:** documents, lab, inventory, messages, dashboard.
- **M5 Pilot ready:** roles, audit viewer, synthetic seed data, demo script, hardening.

## Phase 0: Foundation (M1)

- [x] S0.1 Repo, tooling, CI: monorepo, linters, type checks, test runners, Docker Compose with PostgreSQL
- [x] S0.2 API skeleton: FastAPI app, config, logging, error format, health check, Alembic baseline, test harness
- [x] S0.3 Web skeleton: Next.js shell, layout, navigation, typed API client, first component tests
- [ ] S0.4 Auth and tenancy: Clinic, User, Role, login, session, `clinic_id` scoping helper, role check dependency
- [ ] S0.5 Walking skeleton: one authenticated screen backed by the DB, running with one command (deployment optional)

## Phase 1: Patients and appointments (M2)

- [ ] S1.0 Clinic day: one clinic, timezone (Asia/Kolkata), weekly working hours, default appointment duration, appointment types. No rooms, no per-clinician rotas, no settings screen
- [ ] S1.1 Patients: create, list, search by name, phone and ID, pagination, audit events on write
- [ ] S1.2 Patient detail: overview, edit, status, audit events on write
- [ ] S1.3 Book appointment: model, availability from the clinic day, clinician assignment, no overlapping appointments for one clinician enforced by a database constraint
- [ ] S1.4 Calendar: day and week views, reschedule, cancel
- [ ] S1.5 Appointment status flow: arrived, in progress, completed, no-show, plus audit events

## Phase 2: Care, follow-ups, recalls (M3)

- [ ] S2.1 Care plan, care items, care sessions (recorded against an arrived or in progress appointment)
- [ ] S2.2 Incomplete care: detect it and create or update the patient's follow-up, so it feeds the one coordinator queue instead of a second list
- [ ] S2.3 Follow-ups: manual create, plus auto-create on session completion only when care is unfinished or the clinician sets a due date
- [ ] S2.4 Coordinator queue: follow-ups with due and overdue calculated from the date, mark contacted, book from the queue
- [ ] S2.5 Recalls: rules, due date calculation, due list, kept separate from the follow-up queue
- [ ] S2.6 Patient timeline: one chronological view of everything above
- [ ] S2.7 Core loop check: end-to-end test and a written click-through of the M3 demo

## Phase 3: Documents and lab (M4)

- [ ] S3.1 Document upload behind a storage interface, attached to a patient
- [ ] S3.2 Document viewer, link documents to follow-ups and appointments
- [ ] S3.3 Lab work: record, statuses, patient and lab views

## Phase 4: Inventory (M4)

- [ ] S4.1 Inventory items, categories, batches, expiry
- [ ] S4.2 Restock and transactions (append-only)
- [ ] S4.3 Procedure resource rules and consumption on care session completion
- [ ] S4.4 Alerts: low stock, expiring soon, out of stock

## Phase 5: Messages and reminders (M4)

- [ ] S5.1 Simulated inbox behind a messaging interface
- [ ] S5.2 Coordinator flow: send message, patient picks a slot, appointment booked
- [ ] S5.3 Reminders: model, states, due list

## Phase 6: Dashboard and analytics (M4)

- [ ] S6.1 Dashboard: today's appointments and attention queues, every number clickable
- [ ] S6.2 Inventory attention on the dashboard
- [ ] S6.3 Footfall and appointment analytics
- [ ] S6.4 Care and follow-up analytics

## Phase 7: Roles and hardening (M5)

- [ ] S7.1 Role-based navigation and access review across all routes
- [ ] S7.2 Validation, empty states, error states
- [ ] S7.3 Audit log viewer, test gaps, seed data, demo script

## Cut candidates

Billing, invoices, payments and financial analytics are out of this roadmap, not cut
candidates. See the non-goals in PRODUCT.md.

Drop these first if time runs short: medicines as a separate module, patient-behavior
analytics, supplier management.

## Notes

- The spec puts RBAC and audit in the last phase. Here role checks start in S0.4, audit
  events start with the first patient write in S1.1, and Phase 7 is a review, not a
  first build. S7.3 builds only the audit viewer.
- Simulated messaging is in Phase 5. Until then, "patient contacted" in S2.4 is a manual
  status the coordinator sets.
- S1.4 and S2.1 are the slices most likely to be too big. Split them when the brief is
  written if the acceptance criteria do not fit one review.
- Lab work in S3.3 uses pending, collected, ready and cancelled. Ready is what puts the
  patient back on the follow-up queue. The spec's longer status list can wait.
- The spec's 220 to 300 hour estimate is optimistic. Track actual hours per slice for the
  first two phases, then rescale the rest.
