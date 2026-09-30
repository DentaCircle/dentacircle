@AGENTS.md

## Claude Code notes

- Skills live in `.claude/skills/`. The loop is `/ship-slice`, then `/ship-build`,
  then a human review, then `/ship-seal`. See README.md in the kit for details.
- Use plan mode for `/ship-slice` and for any change to the architecture.
- Prefer small commits inside a slice branch so the diff is easy to review in pieces.
