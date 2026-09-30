# ROADMAP.md

The tracker. Phases are made of slices. A slice is one reviewable change, about half a day
to a day of work, with a visible result. Tick a slice only after `/ship-seal`.

**Now:** S0.1 (not started)

Milestones are demoable. Each one is a real stopping point.

- **M1 Walking skeleton:** login works, one clinic-scoped screen reads real data, CI is green.
- **M2 Front desk:** patients and appointments are usable day to day.
- **M3 Core loop:** the loop in PRODUCT.md works end to end. This is the first real demo.
- **M4 Connected clinic:** documents, lab, inventory, messages, dashboard.
- **M5 Pilot ready:** roles, audit, seed data, demo script, hardening.

## Phase 0: Foundation (M1)

- [ ] S0.1 Repo, tooling, CI: monorepo, linters, type checks, test runners, Docker Compose with the database
- [ ] S0.2 API skeleton: FastAPI app, config, logging, error format, health check, Alembic baseline, test harness
- [ ] S0.3 Web skeleton: Next.js shell, layout, navigation, typed API client, first component tests
- [ ] S0.4 Auth and tenancy: Clinic, User, Role, login, session, `clinic_id` scoping helper, role check dependency
- [ ] S0.5 Walking skeleton: one authenticated screen backed by the DB, running with one command (deployment optional)

## Phase 1: Patients and appointments (M2)

- [ ] S1.1 Patients: create, list, search by name, phone and ID, pagination
- [ ] S1.2 Patient detail: overview, edit, status
- [ ] S1.3 Book appointment: model, availability and conflict rules, clinician assignment
- [ ] S1.4 Calendar: day and week views, reschedule, cancel
- [ ] S1.5 Appointment status flow: arrived, in progress, completed, no-show, plus audit events

## Phase 2: Care, follow-ups, recalls (M3)

- [ ] S2.1 Care plan, care items, care sessions (recorded against an appointment)
- [ ] S2.2 Incomplete care: detect and list
- [ ] S2.3 Follow-ups: manual create, plus auto-create when a session completes
- [ ] S2.4 Coordinator queue: due and overdue follow-ups, mark contacted, book from the queue
- [ ] S2.5 Recalls: rules, due date calculation, due list
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

Drop these first if time runs short: lightweight billing and invoices, medicines as a
separate module, patient-behavior and financial analytics, supplier management.

## Notes

- The spec puts RBAC and audit in the last phase. Here the basics are enforced from S0.4
  and from S1.5 onward, and Phase 7 is a review, not a first build.
- Simulated messaging is in Phase 5. Until then, "patient contacted" in S2.4 is a manual
  status the coordinator sets.
- The spec's 220 to 300 hour estimate is optimistic. Track actual hours per slice for the
  first two phases, then rescale the rest.
