# AGENTS.md

Rules for any AI agent working in this repo. Read PRODUCT.md (scope and decisions) and
ROADMAP.md (phases and slices) before doing anything. Keep this file short. If a rule
stops being useful, propose removing it.

## Working agreement

- Work happens in slices. A slice has a brief in `.shipit/slices/` with status `approved`.
  Do not write feature code for a slice whose brief is not approved.
- One slice is one branch (`slice/S1.3-book-appointment`) and one reviewable change.
- The developer reviews the diff before anything is sealed. Never merge, never mark a
  slice done, never tick ROADMAP.md without the developer saying the review is approved.
- Do not add a dependency, change the stack, or change scope without asking first.
- If the brief turns out to be wrong or too big, stop and say so. Do not quietly widen it.

## Architecture (modular monolith)

- Backend layers: `api` (routes) -> `services` (use cases and business rules) ->
  `repositories` (data access) -> `models`. Domain rules live in `domain/` and `services/`.
- Routes stay thin: parse input, check permission, call one service, return a schema.
  No business rules and no direct DB queries in routes.
- Anything external (AI, messaging, storage, telephony, payments) sits behind an interface
  in `integrations/`. Core code never imports a provider SDK directly.
- Frontend code is grouped by feature under `apps/web/features/`. Shared UI goes in
  `components/`. The frontend never holds business rules that the API must also enforce.
- Schema changes only through Alembic migrations. Never edit the DB by hand or rely on
  auto-create in real code paths.

## Safety rules (never bend these)

- LLM output never changes business state directly. Booking, rescheduling, cancelling,
  care status, follow-ups and stock changes go through validated service methods.
- No diagnosis, treatment recommendation, prescription or clinical interpretation.
  Clinical questions escalate to a clinician.
- Tenancy: every clinic-owned row has `clinic_id`, and every repository query is scoped
  by it. A missing scope is a bug, not a style issue.
- Authorization is deny by default. Every route declares the roles that may call it.
- Audit: create, update, status change and delete on patient, appointment, care,
  follow-up and inventory data write an `AuditEvent` with who, what and when.
- Patient data never goes into logs, error messages, fixtures or screenshots.
  Seed and test data is synthetic only. Secrets never go in git.

## Quality bar

- Every acceptance criterion in the brief maps to at least one automated test.
- Business rules get service-level tests. Endpoints get API integration tests.
  Bug fixes start with a failing regression test.
- Lint, type check and tests must pass before a slice is handed over for review.
  Report anything you could not run instead of saying it passed.
- Keep functions small, type everything, and prefer boring code over clever code.
  The developer must be able to read and explain every line.

## Stops: ask before doing these

- New dependency, new service, or new external account.
- A migration that changes or removes existing tables or columns.
- Anything touching auth, sessions, tenancy scoping, or role checks beyond the brief.
- Adding an AI call anywhere in the product.
- Deviating from the approved brief in any way.
