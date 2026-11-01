# UI.4 Dashboard hierarchy

Status: approved
Proposed branch: slice/UI.4-dashboard-hierarchy
Size: M

## Goal

Put today's appointments and work requiring attention ahead of decorative content while preserving the existing dashboard's data and role behavior.

## Acceptance criteria

1. Replace the large daily brief banner with a compact clinic-local date and heading; preserve access to the calendar.
2. Prioritize today's appointment preview and follow-up attention ahead of decorative and repeated shortcuts at desktop and mobile widths.
3. Preserve accurate totals, links, unavailable and empty states, existing permissions and the inventory-only overview.
4. The dashboard remains usable with keyboard navigation and without horizontal overflow.

## Scope and verification

Presentation only, no dependencies, API, permissions or business-rule changes. Map criteria to automated component tests, run web lint, type check and tests, and capture populated and empty synthetic dashboard proof at desktop and mobile sizes. Coordinate this slice with the existing unsealed UI.1 work; preserve all unrelated changes.
