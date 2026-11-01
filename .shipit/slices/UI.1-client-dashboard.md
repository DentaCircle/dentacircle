# UI.1 Client presentation dashboard

Status: built
Branch: slice/UI.1-client-dashboard
Size: M

## Goal

Present the existing clinic coordination product through a polished, professional dashboard and consistent application shell, preserving workflows delivered through S4.3.

## Acceptance criteria

1. The authenticated shell provides professional desktop and mobile navigation, current-route indication, clinic and user identity, and working sign-out; existing destinations remain reachable.
2. The dashboard shows today's appointments in clinic-local time, with appointment status and links to the existing calendar and patient workflows, using existing authorized APIs.
3. Follow-up and recall Due totals and open lab work link to their existing queues. Displayed totals come from API totals or complete results, never a partial page. Requests only use the user's existing permissions.
4. Register patient, find patient, and calendar shortcuts lead to existing workflows. Inventory users receive an appropriate overview linking to existing inventory screens without requests for patient data they cannot access.
5. Empty, loading where applicable, and failed sections communicate their state accurately; unavailable data never appears as zero. No invented metrics, patients, trends, alerts, or unsupported capabilities.
6. Shared colors, typography, spacing, controls, and surface styling improve the presentation of existing screens without changing their actions, validation, forms, or business behavior.
7. Responsive layout and keyboard-accessible navigation work without horizontal overflow at mobile and desktop sizes.

## Changes

- Data: none.
- API: reuse existing read endpoints and role helpers; no new endpoints or permissions.
- UI: dashboard feature components, authenticated shell/navigation, and shared styling. Calm teal, slate text, light neutral background, white panels, restrained accents, generous spacing, and clear information hierarchy. Retain shadcn/Radix, Tailwind, and installed Lucide icons.
- Migrations: none.

## Out of scope

New dependencies, stack changes, new business workflows, messaging, AI, billing, analytics, stock alerts, permission changes, backend changes, and comprehensive rewrites of individual feature screens. This brings forward only the dashboard presentation needed for the client meeting; it does not mark S6.1 or another roadmap slice complete.

## Decisions and risks

- Developer approval of this brief authorizes the UI scope above before implementation.
- Preserve all unrelated working-tree changes.
- Shared styling affects many screens; inspect representative forms, lists, and detail pages.
- Keep role checks unchanged and reuse the existing authorized read paths.
- The developer reviews the final diff; do not seal, merge, or tick the roadmap without explicit review approval.

## How it will be verified

- Map each acceptance criterion to automated component/page tests, including permissions, real totals, errors, empty states, and navigation.
- Run web lint, TypeScript, Vitest, and a production build where the environment permits.
- Inspect desktop and mobile dashboard and representative existing screens using synthetic local demo data.
- Visual proof in `.shipit/proof/UI.1/`: desktop dashboard populated; mobile dashboard/navigation; empty or unavailable dashboard sections; representative existing patient/calendar screen; inventory-role overview.

## Review packet (filled in by /ship-build)

Implementation is ready for developer diff review; not sealed or merged.

Files in review order:

1. `apps/web/features/dashboard/load-dashboard.ts`: authorized existing read APIs, clinic-local date, independent unavailable states, API pagination totals.
2. `apps/web/features/dashboard/dashboard-screen.tsx`: daily brief, real metrics, six-visit agenda preview, follow-up preview, queue shortcuts, inventory-only overview.
3. `apps/web/components/app-shell.tsx`, `main-nav.tsx`, `mobile-nav.tsx`: shell, icons, active-route presentation, accessible identity/skip link, mobile drawer.
4. `apps/web/app/globals.css`: shared teal/slate tokens, shell/dashboard presentation, existing form/list surfaces, responsive breakpoints.
5. `apps/web/app/(app)/page.tsx`, `loading.tsx`: server composition and motion-aware loading skeleton.
6. Dashboard, shell, loading and page tests; screenshots and verification notes in `.shipit/proof/UI.1/README.md`.

Decisions:

- Keep shadcn/Radix, Tailwind and existing Lucide icons; no new dependencies.
- Keep all existing routes, role helpers, session handling, mutations and backend code.
- Show unavailable sections as unavailable, never zero; use server totals for paginated queues.
- Use a clearly bounded six-appointment and three-follow-up preview, with links to full lists.
- Inventory-only users make no patient, calendar, or coordination requests. Existing navigation destinations are retained; the Phase 7 navigation access review remains deferred.
- Visual proof uses only synthetic HTTP fixtures with the actual web app. No fixture server or fake data is wired into the delivered product.

Acceptance criterion mapping:

1. Existing main/mobile navigation tests plus updated app-shell identity, sign-out, current route and skip-link assertions.
2. Dashboard loader clinic-local UTC-boundary test and sorted agenda, wall-time, patient-link and status rendering tests.
3. Loader/view tests use totals beyond one page and assert all queue destinations and permission behavior.
4. Shortcut and inventory-only view tests plus loader tests proving no unauthorized data requests.
5. Empty, partial-failure, invalid-timezone and loading tests.
6. Existing patient, booking, appointment status, document, inventory, care, queue and session tests pass; representative screens inspected in browser.
7. Existing mobile drawer test, shell breakpoint assertions and manual 320/390/1024/1440px overflow/navigation checks.

Checks:

- Web ESLint: passed.
- Web TypeScript: passed.
- Web Vitest: 285 passed across 61 files, using `pnpm --dir apps/web test --maxWorkers=2`.
- API Ruff and formatting: passed, 237 files formatted.
- API mypy: passed, 216 source files.
- API pytest: 226 passed, 755 skipped because no database URL was configured; database integration coverage is not claimed.
- Production build: passed with `pnpm --dir apps/web exec next build --webpack`; all existing routes compiled.
- `git diff --check`: passed.

Environment notes: the first unrestricted-concurrency web test run exhausted available temporary disk space. After removing only generated Next.js cache and reducing test workers, the full web suite passed. Default Turbopack production compilation could not bind its local worker port in this environment, including on retry with escalation. The Webpack production build passed without changing repository build scripts.

Visual proof and click-through: `.shipit/proof/UI.1/README.md`.

Developer review remains required before sealing, creating the final slice PR, or changing roadmap completion.
