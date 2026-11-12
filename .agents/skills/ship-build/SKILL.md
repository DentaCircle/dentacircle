---
name: ship-build
description: >-
  Build an approved slice. Use when a slice brief has Status approved and the developer
  asks to build or continue it. Works on a slice branch, adds tests, runs checks, then
  stops with a review packet. Never merges or marks work done.
---

# Build

Implement exactly what the approved brief says, verify it, and hand it over for review.

## Execution agreement

An approved brief plus a request to build authorizes the full build through tests,
checks, proof and the review packet. Continue until that handover is complete or a
specific blocker needs the developer. Do not stop after planning, scaffolding, a layer,
a commit or a failed check to ask whether to continue. Small steps are implementation
steps, not approval checkpoints. Send progress updates while continuing the work.

Keep working in the same turn across implementation, tests, fixes, proof and the review
packet. A progress report is not a handover: do not end the turn with an incomplete
status just because the slice is large, time has passed, a test failed, or a difficult
implementation detail remains. Investigate and implement the next authorized step.
A newly discovered problem is not a blocker while a solution within the approved scope
and available permissions remains to be tried. Do not ask the developer to say
"continue" to resume work they already authorized.

Before stopping with an incomplete slice, identify the specific stopping rule or
external limitation, show the evidence and attempts, and state what only the developer
or an external change can resolve. If there is no such reason, continue the build. If a
technical interruption prevents further work, report it honestly; never call the slice
built or imply that a progress report completed the requested work.

Use decisions and permissions already recorded in the approved brief or conversation;
do not ask for the same approval again. Resolve routine implementation choices within
the brief and record meaningful decisions in the review packet. Approval does not
authorize unrelated external actions or override execution permissions.

## Preconditions

- For a new build, the brief exists in `.shipit/slices/` with `Status: approved`.
  If approval is missing, use ship-slice. When continuing an approved build or making
  requested review changes to a `built` slice, inspect the existing work and resume
  what remains; do not restart planning or demand a new brief approval.
- Read AGENTS.md again. Its rules apply to every line you write.
- Create or switch to the branch named in the brief.

## Build

1. Turn each acceptance criterion into a test first where practical.
   Business rules get service tests. Endpoints get API tests.
2. Implement in small steps. Commit at sensible points with clear messages so the diff
   can be reviewed in pieces.
3. Follow the layers in AGENTS.md. Check tenancy scoping, role checks and audit events
   on every new endpoint and query.
4. Run the repo's own commands for lint, type check and tests. Fix failures. Do not
   weaken a criterion or skip a test to get green.
5. Diagnose failures and fix them within the approved scope. A failed command or test
   is a reason to investigate, not an automatic handover. Try a different approach
   when the evidence supports it; do not repeat an unchanged failing action.
   Pause only for a required scope/authorization decision, a brief that is wrong or
   too big, an explicit brief stop, or a concrete blocker that cannot be resolved
   within existing permissions. Explain the blocker, evidence, attempts and exact
   input needed. Complete independent authorized work while waiting, unless the
   blocker invalidates the slice's design or scope.

## Report three things separately

- **Verified:** assertions that pass and would fail if the behavior broke. List commands
  and real results.
- **Evidence collected:** screenshots, sample responses, anything the developer must look at.
- **Judgment pending:** things a test cannot decide, such as UX or naming.

Say plainly what you could not run.
If a check or proof step needs unavailable credentials, pairing or another human action,
complete the remaining work and report the missing evidence precisely. Do not claim
the slice is fully verified or set `Status: built` with required checks or proof missing.

## Collect proof

A slice with a visible change needs screenshots of the real app running on synthetic data,
as listed in the brief. Save them in `.shipit/proof/<slice>/` as `NN-name.png`, with an
`index.md` that gives each image a caption, the steps that produced it, and the commit
hash it was taken at. Commit the folder on its own. The PR is built from it at seal time,
so a missing or stale shot blocks the PR. For an API-only slice, save sample requests and
responses instead. Never include real patient data.

## Write the review packet

Fill the "Review packet" section of the brief, and show it in chat:

- **Files in review order.** Risk first: migrations, models, services and domain rules,
  authorization and tenancy, then routes, then UI, then tests, generated files last.
  One line per file on what to look for.
- **Decisions made** that the brief did not settle, with the reason.
- **Unsure points.** Places where you guessed or where the code is subtle.
- **Click-through.** Exact steps to run the app and see the feature work.
- **Checklist result.** Go through `review-checklist.md` in this folder and note any item
  that fails or does not apply.

Once implementation, required checks, proof and the review packet are complete,
set `Status: built`. Stop with the review packet. If the developer asks for review
changes to a built slice, first set its brief back to `Status: approved`, make and verify
the requested changes, then set it to `Status: built` again and refresh the review packet.
Do not seal unless the developer asks to seal. Do not mark the slice done or tick
ROADMAP.md until the developer explicitly says the review is approved.

Use plain words and short instructions.
