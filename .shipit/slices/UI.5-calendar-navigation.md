# UI.5 Calendar navigation and empty states

Status: approved
Proposed branch: slice/UI.5-calendar-navigation
Size: S–M

## Goal

Help staff move to a requested calendar date and start a booking when the calendar is empty.

## Acceptance criteria

1. Calendar offers a direct date selection that preserves the selected day/week view and clinician filter, with existing previous, next and today controls retained.
2. Calendar provides a clearly labeled booking entry that leads to existing patient selection, without inventing a patient or altering booking rules.
3. An empty calendar identifies the selected date and offers a useful next step; the empty follow-up queue explains how to view all open follow-ups and where a follow-up is created through existing workflows.
4. Navigation works by keyboard and at mobile and desktop widths; existing access control and errors remain unchanged.

## Scope and verification

No new dependency, migration, API or permissions. Map criteria to automated tests; run web lint, type check and tests. Capture calendar and queue empty states using synthetic data on desktop and mobile.
