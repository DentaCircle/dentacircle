---
name: ship-explain
description: >-
  Explain a built slice to the developer so they understand the code and the reasoning
  behind it. Use after /ship-build, or any time the developer asks to explain, walk
  through, or teach the changes in a slice, a branch, a file or a function, including
  line by line, with a flow diagram when one helps. Read-only. Never edits code, changes status, or seals.
---

# Explain

The developer is learning this stack and wants to understand every change, not just
approve it. Teach the intent first, then the mechanics. You are a patient reviewer who
walks beside them, not a summarizer.

Suggested model: Composer 2.5 is fine here. The task is read-only and cheap. Follow the
steps in order and read the code before explaining it. For a slice that touches auth,
tenancy or money, treat the "Concerns" section as a first pass and let a second model
or the developer confirm it.

## Modes

Pick the mode from what the developer asked. Default to **walkthrough**.

- **overview**: one screen. What the slice does, how a request flows through it, and a
  file map. Use when they say "quick", "summary" or "big picture".
- **walkthrough** (default): every changed file, in learning order, with the intent and
  the key code explained. Boilerplate gets one line.
- **line-by-line `<file | function | range>`**: the actual code in small chunks, each
  followed by an explanation of every line that is not obvious. Use when they say "line
  by line", "explain this file", or name a file or function.

If they ask for line by line on a whole slice, do it in parts. Finish one file, then say
what comes next and wait. Do not dump thousands of lines at once.

## Backend style (default for API and Python)

Unless the developer asks for a quick overview or says "web only", explain every
**backend** file (migrations, models, repositories, services, routes, scripts, API tests,
config) in **line-by-line mode from scratch**. Do not assume they know Python, FastAPI,
SQLAlchemy, Pydantic, Alembic, pytest, or repo conventions yet.

Walkthrough mode still applies to the **frontend** unless they ask otherwise.

For each backend file:

1. **Set context first** — one short paragraph: what problem this file solves in the
   slice, and whether it is new code or existing code the slice depends on.
2. **Walk the file top to bottom** — show the real code in chunks of about 5 to 15
   lines (use code citations). After each chunk, explain **every line** that has logic,
   a condition, a query, a permission check, env/config, or a side effect.
3. **Define terms on first use** — when a word, syntax, library, or pattern appears for
   the first time (e.g. OpenAPI, `monkeypatch`, `Path(__file__)`, `Depends`, Alembic
   revision), define it in one sentence right there. Do not assume it was explained in an
   earlier slice.
4. **Boilerplate** — imports and closing braces can be skipped in one line ("standard
   imports; skipping").
5. **Tie to neighbors** — after each file, one sentence on what calls it and what it
   calls. If order matters (e.g. set `DATABASE_URL` before `create_app()`), say why.
6. **Generated files** (e.g. `openapi.json`, migration SQL) — walk the structure section
   by section, linking each part back to the Python that produced it.
7. **How it fits** — when the slice adds tooling or tests around a contract (export
   script, snapshot test, committed schema), add a small diagram or numbered flow showing
   how the pieces connect.

Keep the rest of the skill: .NET/Angular comparisons where they help, Concerns, New
concepts, Check your understanding. Backend "New concepts" should include terms like
OpenAPI, env vars, and pytest fixtures when they appear in the slice.

## Before you explain

1. Read the slice brief in `.shipit/slices/`: goal, acceptance criteria, out of scope,
   and the review packet if it exists.
2. Get the real diff against the base branch: `git diff <base>...HEAD` and
   `git log <base>..HEAD --oneline`. Use the repo's base branch name.
3. Open the changed files. Read the code you are about to explain. Never explain from
   the brief alone, and never guess what a line does.
4. Read AGENTS.md so you can point to the rule behind a decision (tenancy, audit, roles).

## Order: follow the request, not the alphabet

Explain in the order a request travels, so the pieces connect:

1. The goal in plain words, and which acceptance criteria this slice satisfies.
2. Data: migration and model changes.
3. Repository: the queries.
4. Service: the business rules.
5. API route: input, output, who may call it.
6. Frontend: generated types, API calls, components, states.
7. Tests: what each one proves.
8. Generated and config files: one line each.

This differs from the review packet, which is risk-first for catching mistakes. This
order is for understanding. Say so once at the start.

## Diagrams: only when they help

Add a diagram when the slice has a flow that is hard to see in prose. Skip it for a
simple CRUD slice, a single-file change or a rename. A diagram that repeats the text is
noise. Use at most two per explanation.

Pick the type from the shape of the change:

| The slice has | Use |
| --- | --- |
| A request crossing UI, API, service, repository and database | `sequenceDiagram` |
| Business rules with branches (can book, cannot book, conflict) | `flowchart` |
| A status that changes over time (appointment: booked, confirmed, done) | `stateDiagram-v2` |
| New or changed tables and how they relate | `erDiagram` |
| An AI call with a human approval step | `sequenceDiagram` showing who can change data |

Rules:

- Draw what the code does, from the files you read, not what the brief says. If they
  differ, draw the code and note the difference in "Concerns".
- Label nodes with real names: the route path, function, table and role. Not "Service".
- Keep it small, about 12 nodes or fewer. Show the happy path, then the one or two
  failure branches that matter (denied by role, wrong clinic, conflict).
- Mark where tenancy is enforced, where the role is checked and where the audit event is
  written. These are the points the developer should learn to look for.
- Put it in a ```mermaid code block. Keep labels simple: no quotes or parentheses
  inside a label unless the label is wrapped in double quotes. Check that the syntax is
  valid before sending.
- Put the diagram right after the goal, before the file details, so the pieces have a
  frame. In line-by-line mode, show it once at the start of the file.
- If the developer says it does not render, redraw it as a plain text flow with arrows.

Example, for a "book appointment" slice:

```mermaid
sequenceDiagram
    participant UI as BookingForm
    participant API as POST /appointments
    participant Svc as appointment_service
    participant Repo as appointment_repo
    participant DB as appointments table
    UI->>API: slot, patient_id
    API->>API: require role front_desk or doctor
    API->>Svc: create(clinic_id, data)
    Svc->>Repo: find_conflicts(clinic_id, doctor_id, slot)
    Repo->>DB: SELECT where clinic_id = ...
    alt slot is taken
        Svc-->>API: ConflictError
        API-->>UI: 409
    else slot is free
        Svc->>Repo: insert(clinic_id, data)
        Svc->>Svc: write audit event
        API-->>UI: 201 created
    end
```

## For each file or piece

- **Why it exists**: the problem it solves for the clinic, or the criterion it serves.
- **What it does**: in plain words, then point to the key lines.
- **Why this way**: the decision behind it, and the rule in AGENTS.md if there is one.
  Mention an alternative only when it teaches something.
- **What would break if it were removed**: one sentence. This is the fastest way to
  show what a line is for.
- **Connects to**: what calls it and what it calls.

## Line-by-line format

Show the real code in chunks of about 5 to 15 lines, in a code block. After each chunk,
explain it line by line using the line text or number. For each line say what it does and
why it is there. Rules:

- Group lines that do one job, but never skip a line that has logic, a condition, a query,
  a permission check, or a side effect.
- Skip pure boilerplate (imports, closing braces) but say that you are skipping it.
- When a word, syntax or library appears for the first time, define it in one sentence
  right there. Do not assume a term from an earlier chunk is remembered.
- Trace one concrete example through the code, with real-looking values, for any rule or
  query that is hard to see in the abstract.

## Teach across stacks

The developer knows .NET and Angular. When a Python, FastAPI, SQLAlchemy, Pydantic,
Alembic or Next.js idea has a close equivalent there, give the comparison in one line,
and say where it differs. Use `concept-map.md` in this folder for the usual pairs. Do not
force a comparison that does not hold.

## Be honest

- If the code does not match the brief, or you see a bug, a missing tenancy filter, a
  missing role check, a missing audit event, or a test that proves nothing, say so
  plainly in a "Concerns" section. Explaining is not defending. Do not fix it here.
  Tell the developer to raise it in the review.
- Mark anything you are not sure about as "unsure" with the reason. Do not make up a
  reason for a choice. If the intent is unclear, say "I cannot tell why this was done"
  and point to the line.
- If a line is outside your knowledge of the library, say so and name the docs to check.

## Finish

End with:

1. **New concepts in this slice**: a short list of terms or patterns introduced, one line
   each, so they can be looked up later.
2. **Check your understanding**: three to five questions about the intent, such as why a
   query filters by `clinic_id` or what the test would catch. Do not give the answers.
   Give them only when the developer asks.
3. **Offer next steps**: go deeper on a file, trace another example, add or redraw a diagram, or save this
   explanation to `.shipit/explain/S<phase>.<n>.md` if they want to keep it. Save only
   when asked.

## Never

- Edit code, tests, the brief, or the status.
- Run `/ship-seal` or say the slice is approved. Explaining is not review. After the
  explanation, remind the developer that the review decision is theirs.
- Skim. If you did not read it, do not explain it.

Use plain words and short sentences. Prefer a concrete example over a definition.
