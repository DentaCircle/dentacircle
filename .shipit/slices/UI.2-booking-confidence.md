# UI.2 Booking confidence

Status: approved
Proposed branch: slice/UI.2-booking-confidence
Size: M

## Goal

Keep the patient and selected appointment details visible while staff book, and make available times easier to understand.

## Acceptance criteria

1. Patient, follow-up and recall booking entry points show the patient's name and clinic-facing ID throughout booking, using existing authorized data. Unavailable identity is reported rather than guessed.
2. Before booking, show the selected patient, appointment type, clinician, date, start and end time or duration, and update the summary when selections change.
3. Label appointment type and booking actions clearly. Group available times into morning and afternoon while preserving selectable availability, keyboard use and existing conflict handling.
4. Keep existing appointment-type and clinician defaults visible in the booking summary; do not change their selection rules without a separate decision.
5. When no times are available, explain practical next steps using the existing date, clinician and appointment-type controls.
6. Existing API validation, permissions, booking outcomes and patient privacy remain intact.

## Scope and verification

No new dependency, migration, API, role change or business rule. First verify existing responses provide the necessary patient identity and duration; if they do not, stop and propose a brief amendment. Map each criterion to automated tests; run web lint, type check and tests. Inspect synthetic-data booking screens at desktop and mobile sizes and save visual proof.
