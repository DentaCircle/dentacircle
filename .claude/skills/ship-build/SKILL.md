---
name: ship-build
description: >-
  Build an approved slice. Use when a slice brief has Status approved and the developer
  asks to build or continue it. Works on a slice branch, adds tests, runs checks, then
  stops with a review packet. Never merges or marks work done.
---

# Build

Implement exactly what the approved brief says, verify it, and hand it over for review.

## Preconditions

- The brief exists in `.shipit/slices/` with `Status: approved`. If not, use ship-slice.
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
5. If you must deviate from the brief (extra table, new dependency, changed behavior),
   stop and ask. If repeated attempts fail, stop, report what you tried, and say what
   is needed.

## Report three things separately

- **Verified:** assertions that pass and would fail if the behavior broke. List commands
  and real results.
- **Evidence collected:** screenshots, sample responses, anything the developer must look at.
- **Judgment pending:** things a test cannot decide, such as UX or naming.

Say plainly what you could not run.

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

Set `Status: built`. Stop. Wait for the developer's review. If they ask for changes,
make them here. Do not seal.

Use plain words and short instructions.
