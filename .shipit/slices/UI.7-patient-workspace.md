# UI.7 Patient workspace

Status: approved
Proposed branch: slice/UI.7-patient-workspace
Size: M

## Goal

Give staff a consistent patient workspace so care, documents, lab work and timeline feel connected and patient identity remains clear across those screens.

## Acceptance criteria

1. The patient overview presents identity, key details, upcoming appointments and the primary booking action with a clear hierarchy. Existing status, edit and booking permissions and outcomes remain unchanged.
2. Overview, care, documents, lab and timeline expose consistent, labeled patient navigation and identify the active section. Existing URLs, deep links, document filters and back/forward behavior continue to work.
3. Patient name and clinic-facing ID remain visible across these sections when authorized data is available; failures and restricted access are shown without exposing patient details or guessing identity.
4. Mobile and desktop layouts remain usable without page-wide horizontal overflow; controls, focus order and navigation are keyboard accessible.
5. Existing care, document, lab, timeline, status and booking behavior remains unchanged, including their loading, error and permission handling.

## Scope and verification

Use existing routes, authorized API reads and installed components. No new dependency, migration, API, permission change or business rules. If patient identity cannot be shared without altering access or duplicating expensive reads, stop and propose an amendment. Map all criteria to component and route tests; run web lint, type check and tests. Capture desktop and mobile proof with synthetic data and inspect deep links and permission-limited states. Build on reviewed predecessor slices so the diff remains separate.
