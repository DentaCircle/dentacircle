# S2.8 proof

Code reviewed from: `slice/S2.8-appointment-client-maintenance`.

Local manual evidence used only synthetic data: Proof Clinic, Proof Desk, and Proof Ada.
The booking form was opened through the running local stack after the database was migrated;
the initial current-day state rendered the expected disabled Book action with no free times.
The browser automation environment could not export its local screenshot into this repository,
so this maintenance-only slice records automated behavioral evidence instead of embedding an
image. It does not claim visual proof beyond that manual check.

- `make check` with configured local PostgreSQL: API 616 passed; web 48 files / 188 tests
  passed.
- Focused booking and rescheduling screens: 22 behavioral tests passed, including stale JSON
  completion/failure, cancellation, selection invalidation, timeout recovery, retry, and both
  appointment conflict messages.
- `pnpm exec next build --webpack`: completed successfully.
