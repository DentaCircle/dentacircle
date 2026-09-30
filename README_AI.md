# Clinic project workflow kit

A lightweight, trackable build process for a solo developer working with an AI coding
agent, adapted from Dan Vega's shipit skills. Where shipit lets the agent keep going
after planning, this version adds two human gates so you review what gets built.

## Set up

1. Create the repo. Copy everything in this kit into the repo root, keeping the hidden
   folders (`.claude/`, `.shipit/`).
2. Put your spec in `docs/Dental_AI_Assistant_Specification.md`.
3. Open PRODUCT.md and settle the Open decisions when their slices come up.
4. Start your agent in the repo and run `/ship-slice`.

Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`. Codex reads `AGENTS.md`
directly. The skills are plain markdown, so copy them to whichever folder your tool
uses if you switch.

## The loop

```text
/ship-slice   agent writes a one-page brief          -> YOU approve the brief
/ship-build   agent builds, tests, writes a packet   -> YOU review the diff
/ship-seal    agent updates tracker and state        (only after your approval)
```

Every slice ends with a tick in ROADMAP.md, so progress is visible at a glance.
Use `/ship-roadmap` at milestones and `/ship-retro` when the process feels heavy.

## The files

| File | Job |
| --- | --- |
| `AGENTS.md` | Rules the agent always follows: architecture, safety, quality, stops |
| `PRODUCT.md` | Current scope, decisions, open decisions, current state. Short. |
| `ROADMAP.md` | Phases, slices, milestones, checkboxes. The tracker. |
| `.shipit/slices/` | One brief per slice, with status draft, approved, built, or done |
| `.shipit/open.md` | Unresolved items with a next action. Created when needed. |
| `.claude/skills/` | The five skills |

## How to review

Read the review packet the agent writes at the end of `/ship-build`. It lists files in
the order that matters (migrations, business rules, access control first, UI later).
Run the click-through steps yourself. Use `ship-build/review-checklist.md` as your
own list. If you cannot explain a piece of code, ask the agent to explain or simplify it
before you approve.

## Differences from shipit

- Added a slice brief and an approval gate before building.
- Added a review gate before sealing, and a `ship-seal` step that updates the tracker.
- Added ROADMAP.md for phases and milestones. Shipit has only PRODUCT.md.
- Dropped shape, prototype, stack and verify as separate skills. Their useful parts are
  folded into `ship-slice` and `ship-build`. Add them back if you miss them.
- Rules are project specific: tenancy, authorization, audit, patient data, and AI safety.
