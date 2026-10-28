# UI.3 Visit and follow-up action hierarchy

Status: approved
Proposed branch: slice/UI.3-visit-and-queue-actions
Size: M

## Goal

Make the next action clear in populated calendar and follow-up rows while retaining server validation and feedback.

## Acceptance criteria

1. Calendar and follow-up rows visually separate patient and visit details from actions, emphasizing the next appropriate action and keeping secondary actions discoverable and keyboard accessible.
2. Status actions use verbs and retain existing confirmations, role restrictions and success/error handling.
3. Retain the existing server validation and explanatory feedback for unavailable arrived and no-show actions. Proactive eligibility is deferred until the API can supply reliable, current eligibility.
4. Follow-up row actions and document links retain their existing destinations and behavior at desktop and mobile sizes.

## Scope and verification

No new dependency, migration, API or permission change. The API remains authoritative for time-sensitive eligibility; no client-side eligibility rules are added. Test each criterion, including role and stale-state behavior. Run web lint, type check and tests, and capture synthetic populated rows on desktop and mobile.
