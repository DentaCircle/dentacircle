# MAINT-1 Appointment booking ownership

Status: draft
Branch: slice/MAINT-1-appointment-booking-ownership
Size: M

## Goal

Direct, follow-up and recall booking share one deep appointment-booking module without
the dependency cycle through appointment status changes, preserving existing behavior.

## Scope and starting point

Optional maintenance after completion of the Phase 0–7 roadmap, outside the M5 gate.
It is not a prerequisite for S3.1, S7.2a or any other roadmap slice. Scheduling was
agreed on 2026-10-23. Revisit sooner only if appointment-booking changes expose material
friction and the developer explicitly reprioritizes this work.
Before building, reassess the cycle, scope and test map against the then-current code,
approve the refreshed brief and capture the latest reviewed revision as the branch base.
Preserve unrelated local edits; do not use the old S2.8 snapshot as the implementation base.

## Acceptance criteria

1. **One booking implementation.** Direct, follow-up and recall booking use the same
   actual booking implementation and result/error identities. The booking module has
   no dependency on appointment status, follow-up or recall orchestration. Queue booking
   no longer imports booking or its result type from the status-owning appointment module,
   including through function-local or type-only reverse imports. Confirm the dependency
   direction in review; exercise all three paths through automated behavior tests.
2. **Scheduling compatibility.** Preserve active-patient, active-clinician/role and
   active-type validation, timezone handling, clinic-local grid, opening intervals,
   type/default duration, date horizon, error precedence and patient/clinician overlap
   rejection. Availability and reschedule keep their original-duration and unchanged
   inactive-clinician behavior. No duplicated scheduling-rule implementation is introduced.
3. **Atomic writes.** Booking writes the same appointment, audit and timeline results.
   Queue booking also writes its booked status, linked appointment and events in the
   caller's transaction. Preserve current flush/refresh timing and exception translation;
   no inner commit, nested transaction, new autoflush, or lock reordering. Failures roll
   back all writes, and simultaneous booking still produces one booking where required.
4. **Lifecycle compatibility.** Completion, cancellation, no-show and reschedule retain
   their existing follow-up and recall effects, including close-before-create and inactive
   patient behavior. Preserve appointment-before-patient locking on status paths and
   patient-before-queue locking on queue booking. Retain the no-autoflush patient lock.
5. **Contract compatibility.** Existing route payloads, statuses, safe errors, roles,
   clinic isolation, timezone serialization and generated schema remain unchanged.
   Existing module imports used by routes/tests may be preserved with direct re-exports;
   do not substitute forwarding functions for moving the actual implementation.

## Changes

- Data and migrations: none.
- Implementation: booking ownership in `apps/api/src/dentacircle/services/`; adapt
  `appointment_service.py`, `follow_up_service.py` and `recall_service.py` to one-way
  dependencies. Minimal import adjustments for existing callers/tests are allowed.
- Interface: retain existing booking inputs and observable results. Booking-specific
  validation and writes belong together; do not expose a collection of setup steps to callers.
- Shared scheduling implementation needed by booking, availability and reschedule must
  remain single-owned below their callers. Use one cohesive internal scheduling module
  if required; never import private helpers back from the status-owning module or copy
  rules into both places. Move only relevant view/error definitions to avoid reverse imports.
- PostgreSQL remains the concrete persistence adapter. No new persistence abstraction,
  external integration, dispatcher or adapter registry is needed.
- Frontend, wire contracts and generated types: unchanged.

## Out of scope

New booking rules, feature changes, query optimization, full appointment decomposition,
follow-up/recall unification, event buses, transaction redesign, auth/session changes,
new role/tenancy behavior, migrations, dependencies and changes to other domain modules.

## Decisions and risks

- This is behavior-preserving. Existing rollback and concurrency coverage is substantial;
  the motivation is locality and navigability, not a claimed correctness defect.
- Deletion test: removing the booking module would redistribute real invariants and writes
  to three callers. Moving only a function while leaving its knowledge in a cycle fails.
- Shared helpers currently support booking, availability, reschedule and upcoming views;
  a naive extraction would either duplicate them or retain the reverse dependency.
- Exception identity must survive re-exports so existing route mappings still catch it.
  Avoid fixing unrelated import cycles (for example patient/timeline) in this slice.
- Preserve transaction ownership, query scoping, role checks and lock semantics exactly.
  If the extraction cannot fit one review without broader changes, stop and revise this brief.

## How it will be verified

Use existing booking/module tests with real PostgreSQL, route integration tests and the
core-loop test as the test surface. Add meaningful characterization coverage only where
an uncovered behavior affected by the move is found. A pure refactor does not require
inventing a failing behavioral regression; any discovered bug needs a failing regression
test and explicit scope approval before its fix. Do not test private helper calls.

Criterion-to-test map:

- 1: direct booking in `test_appointment_service.py`/`test_appointment_routes.py`, queue
  booking in `test_follow_up_book.py` and `test_recall_actions.py`; inspect imports for
  the required dependency direction, with typecheck verifying moved contracts.
- 2: `test_appointment_service.py`, `test_appointment_availability.py`,
  `test_appointment_slots.py`, `test_appointment_reschedule.py` and route conflict cases.
- 3: `test_appointment_audit.py`, `test_appointment_concurrency.py`,
  `test_appointment_move_concurrency.py`, `test_follow_up_book.py`,
  `test_follow_up_queue_concurrency.py`, recall audit/booking tests and timeline writes.
- 4: follow-up close, release, completion-date and close-concurrency suites;
  `test_recall_on_completion.py`, appointment status-concurrency tests,
  `test_timeline_loop.py` and `test_core_loop.py`.
- 5: appointment/follow-up/recall route suites for role and clinic isolation,
  plus unchanged OpenAPI/schema diff and strict mypy.

Run affected suites during extraction, then `make check` with configured PostgreSQL.
No frontend changes are intended; run `make web-build` with API_BASE_URL configured as
the final compatibility check. Report skipped/unavailable checks and never print secrets.

Synthetic request/response proof in `.shipit/proof/MAINT-1/`:

- Direct, follow-up and recall booking success with linked queue status.
- Patient and clinician overlap rejection with no extra writes.
- Completing a booked visit closes the old task and produces the expected next task.
- Cancellation/no-show releases booked tasks; reschedule keeps them linked.

Record automated rollback/concurrency results in the proof index; sample responses alone
do not establish atomicity. Review the implementation against this approved brief and
repo standards using code-review. After developer diff approval, prepare the PR from
the template with proof embedded, or provide the compare link. Never merge, mark done
or tick ROADMAP.md without explicit review approval. Do not publish external messages
without separate authorization.

## Review packet

Not built. Optional post-roadmap work; base revision will be selected if scheduled.
No checks or proof claimed yet.
