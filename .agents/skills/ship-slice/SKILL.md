---
name: ship-slice
description: >-
  Plan the next slice of work. Use when the developer asks what to build next, names a
  slice from ROADMAP.md, or wants a brief written before building. Writes a slice brief
  and stops for approval. Never writes feature code.
---

# Slice

Turn one roadmap item into a short brief the developer can approve in a few minutes.

## Read first

Read PRODUCT.md, ROADMAP.md, AGENTS.md and `.shipit/open.md` if it exists. Read the code
the slice will touch. Use the spec in `docs/` for detail on the module, not as a to-do list.

## Pick the slice

Use the slice the developer names. Otherwise take the first unticked slice in ROADMAP.md.
If earlier slices are unfinished or `.shipit/open.md` has blockers, say so first.

## Write the brief

Copy `.shipit/slices/_template.md` to `.shipit/slices/S<id>-<name>.md` and fill it in.

- Keep it to about one page. Plain words. No filler sections.
- Acceptance criteria must be testable. If you cannot imagine the test, rewrite the criterion.
- List every data, API and migration change so the developer can approve the schema here.
- Name what is out of scope. Pull in nothing from later slices.
- If the slice is bigger than one reviewable change, split it and update ROADMAP.md
  after the developer agrees.
- If a material choice is open (see Open decisions in PRODUCT.md, or a new dependency),
  give a recommendation and the tradeoff in one short paragraph. Do not decide it silently.
- Set `Status: draft`.

## Stop

Summarize the brief in a few lines and ask for approval or changes.
Do not start building. When the developer approves, set `Status: approved`.
Record any decision they make in PRODUCT.md.

Use plain words and short instructions.
