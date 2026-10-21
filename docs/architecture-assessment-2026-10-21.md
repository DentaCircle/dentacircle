# Architecture assessment — 21 October 2026

Assessment only. The proposed implementation requires approval of
`.shipit/slices/S2.8-appointment-client-maintenance.md`. No product code changed.
Assessed against working-tree AGENTS.md, PRODUCT.md, ROADMAP.md, the Cursor rules,
and briefs S0.3, S1.3, S1.4, S2.4, S2.4b, S2.5 and S2.7. No glossary or ADR directory exists.
The modular monolith and the existing stack remain the constraints.

## 1. Separate shared transport from feature contracts — strong

**Evidence.** `apps/web/lib/api/client.ts:444` (`getJson`), `:470` (`sendEmpty`)
and `:489` (`sendJson`) repeat fetch, response/error handling and five-second timeout
logic. The same file owns health, auth, patients, appointments, care, follow-ups,
recalls and timeline contracts and runtime parsers. This is divergent change, rather
than a problem with its line count. New feature work repeatedly edits the shared module.
`HealthResponse`, `CurrentUser`, `Patient` and `PatientPage` reuse generated types
at lines 13–16, while `CalendarVisit` (83), `CarePlan` (135) and `TimelineKind` (196)
are handwritten despite generated equivalents. Some are intentional projections;
blindly replacing them with full wire types would misrepresent what the parser validates.

**Possible designs.**

- Keep the module together and consolidate its three request implementations. Lowest
  diff, but feature contracts and parsing continue to accumulate in one place.
- Extract a shared transport module; put new/touched feature contracts and parsers
  beside their feature. Keep `client.ts` exports compatible during gradual migration.
  A concrete fetch adapter is sufficient; no provider registry or dependency injection
  framework is warranted. This gives locality to HTTP policy and feature behavior.
- Move every endpoint now, or add a generated runtime client/schema library. Wider
  review, import churn and, for a library, dependency approval; unnecessary for this task.

**Recommendation.** Use the second design incrementally. First extract existing transport
without changing its server URL, cookie forwarding, browser credentials, no-store policy,
error result or timeout behavior. Add only the touched appointment browser operations in
`features/appointments/`. Keep existing feature endpoints/parsers in `client.ts` this time.
Reuse generated request types and explicit projections for validated response data.
Generated TypeScript does not validate network data: preserve runtime parsing.

**Depth and tests.** The transport interface hides request mechanics; the feature
interface hides wire names and validation. Deleting the transport would redistribute
error/timeout policy to callers, so it earns its seam. Test callers through their
public interface with a controlled fetch adapter; do not test file layout or private parsers.
The leverage is shared policy, not an additional forwarding module per function.

## 2. Own availability lifecycle once; keep forms distinct — strong

**Evidence.** `BookScreen` in `apps/web/features/appointments/book-screen.tsx:45`
and `RescheduleScreen` in `reschedule-screen.tsx:43` duplicate the effect: construct
query, abort old request, clear slots, load, parse, preserve selection only if still
available, and map forbidden/closed/empty/ready/error states. The only material query
difference is appointment type versus reschedule appointment id.
`time-slots.tsx:44` also mixes network parsing with rendering.

Both effects abort on cleanup, but neither checks a request generation or aborted
signal after `await response.json()`. A response whose body finishes decoding after
the selection changes can still publish old slots or errors. Both submit handlers use
a ref as well as disabled state for duplicate-submission protection; retain that.
Neither availability nor submit fetch has a timeout, unlike shared transport.

`BookScreen:120` treats remaining 409s, including `patient_busy`, as a clinician slot
being taken. `RescheduleScreen:108` treats every 409 alike and does not inspect its
code. The backend already distinguishes these errors in `api/appointments.py:313–318`.

**Possible designs.**

- Share only fetch/query construction. Small, but both callers still implement the
  cancellation, stale-response and selection state machine; fixes still happen twice.
- A feature-local availability hook owns that lifecycle, accepting booking or reschedule
  inputs and exposing state, slots, selection and reload. Keep `TimeSlots` presentational
  and keep each form's payload, terminal states and redirect explicit.
- A universal booking/reschedule form or general data-fetching framework. This couples
  different workflow decisions and expands the interface with flags. No new library is needed.

**Recommendation.** Choose the feature-local hook. Couple it to the appointment request
module from candidate 1, using the existing fetch seam in tests. This increases depth:
forms ask for availability rather than coordinating requests. Locality puts stale-result
guards, selection validity and retry behavior together. The leverage is two real callers,
including all three booking entry points that already share BookScreen.

**Behavior to retain or explicitly improve.** Preserve query modes, clinic wall-time
labels, closed/empty/forbidden/error messages, queue terminal behavior, reschedule's
omission of an unchanged clinician, URLs and redirects. Add explicit stale-response
protection and apply the existing five-second policy to these previously unbounded
requests. Distinguish patient conflicts from clinician conflicts with fixed text;
do not display raw backend messages. A timed-out mutation has an uncertain outcome:
never automatically retry it. Test rapid input changes, delayed JSON, cleanup, reload,
timeouts, conflict codes and double submit through both rendered forms.

## 3. Remove the appointment/follow-up/recall dependency cycle — worth exploring

**Evidence.** `apps/api/src/dentacircle/services/appointment_service.py:227`
(`change_status`) coordinates follow-up and recall outcomes; `cancel_appointment:184`
releases both. Yet `follow_up_service.py:462` (`book_follow_up`) and
`recall_service.py:310` (`book_recall`) import `book_appointment` locally from that
same appointment module. The local imports avoid import-time failure but leave a
bidirectional dependency. Booking, availability, calendar reads and status changes
therefore pull in coordination they do not all need.

Not all of this is friction: availability and booking correctly share pure scheduling
rules in `domain/appointment.py`. Reads already use clinic-scoped repositories.
`record_incomplete_care` closes a booked follow-up before creating the next one;
`record_recall` likewise closes before creating. Status/cancel paths lock the visit
before the patient and queue rows; `patient_lock.py` deliberately suppresses autoflush
to avoid flushing pending timeline inserts while acquiring the patient lock.
These are correctness requirements, not incidental implementation details.

**Possible designs.**

- Keep the cohesive appointment module and documented local imports. Least risk;
  acceptable until its callers change again, but the cycle remains.
- Move appointment placement (booking, validation it needs, overlap error mapping and
  its small result contract) into a lower-level module that knows nothing about queues.
  Appointment orchestration and both queue-booking modules call that interface. Keep
  transaction ownership where it is, with no extra commits, flushes or lock reordering.
- Separate every operation into a module, or dispatch lifecycle events on a bus.
  The first risks scattered invariants; the second obscures mandatory synchronous
  ordering and atomic audit/timeline/queue writes. Neither follows from the evidence.

**Recommendation.** Explore the placement extraction in a separate approved slice after
the frontend work. Its goal must be removing the dependency cycle, not reducing file size.
Do not also split availability, calendar, statuses and view mapping just because they
coexist. The deletion test rejects a collection of shallow pass-through modules.
There is one database adapter; a generic scheduling port is speculative. The gain is
locality of placement rules and leverage for three booking callers behind a smaller interface.

**Validation required later.** Existing PostgreSQL service and route tests, booking and
move concurrency tests, rollback-on-audit-failure tests, queue close/release tests and
`test_core_loop.py`. Assert behavior through service/HTTP interfaces. Preserve role
checks, clinic scopes, exception mapping, row-lock order and commit ownership exactly.

## Recommended first slice

S2.8 combines the minimal transport extraction from candidate 1 with the shared
availability lifecycle from candidate 2. They address the same request-policy defect;
neither a full client migration nor backend restructuring is included. See the draft
brief for exact scope and behavioral test seams. Next recommendation: gradually move
appointment read contracts/parsers out of `client.ts`; consider the backend cycle in
its own slice when appointment coordination is next touched.

## Setup and baseline evidence

- Skills CLI project/global inventory: none of the four requested skills installed;
  global Cursor skills were `teach` and `find-skills`, and project ship skills targeted Claude.
- Installed only `improve-codebase-architecture`, `codebase-design`, `tdd`, `code-review`
  using `npx --yes skills@latest add mattpocock/skills --skill ... --agent cursor --yes`.
  CLI verified all four target Cursor under `.agents/skills/`; `skills-lock.json` records hashes.
- Read their instructions plus the architecture HTML guide, design deepening guide,
  and TDD testing/mocking guides. The architecture skill's required `codebase-design`
  dependency is included. Conditional interview/domain-document skills are not used;
  this task already defines the assessment and brief workflow. No runtime dependency added.
- Existing web suite: 48 test files, 179 tests passed. The pnpm test invocation forwarded
  a `--`, so Vitest ran the entire suite rather than only the requested paths.
- No implementation, new regression tests, full `make check`, backend tests, frontend
  build or implementation diff review yet. These follow approved scope, not this assessment.
- Initial implementation base candidate: `80c4fb0982c68f21337b990114f85ecbe5a64170`.
  Existing user edits are preserved. No issue, comment, PR or other external message published.
