# UI.6 Workspace copy and duplication

Status: approved
Proposed branch: slice/UI.6-workspace-copy
Size: S

## Goal

Remove decorative slogans and unnecessary repeated navigation from the shared workspace so clinic staff see task-relevant information.

## Acceptance criteria

1. The shared desktop and mobile shell contains no slogans such as “Every step, connected” or “Your clinic. One workspace.” Clinic identity, user identity, sign-out, skip navigation and all existing destinations remain available.
2. Remove repeated navigation or explanatory copy only where the same action remains easy to discover in context. Keep information that explains an empty, error or permission state.
3. Desktop and mobile navigation remain accessible by keyboard, with visible focus and current-route indication.

## Scope and verification

Presentation and copy only; no new dependencies, API changes, permissions or workflows. Map each criterion to automated tests; run web lint, type check and tests. Verify desktop and mobile navigation and capture visual proof with synthetic data. Build against the reviewed UI.1 shell and the dashboard slice; do not silently combine their changes.
