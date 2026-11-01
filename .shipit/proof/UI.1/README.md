# UI.1 visual proof

All people, clinic details, appointments, and queues in these images are synthetic.
Screenshots were captured from the actual Next.js app using an isolated temporary HTTP
fixture server through the existing validated API client. No demo responses or data were
added to the product, no environment files were changed, and both temporary servers were
stopped after verification. This is presentation verification, not a live database test.

- `01-desktop-dashboard.png`: populated coordination dashboard, 1440px viewport.
- `02-mobile-dashboard.png`: populated dashboard, 390px viewport, full page.
- `03-mobile-navigation.png`: mobile drawer, current route and existing destinations.
- `04-patients-desktop.png`: existing patient list with the shared presentation.
- `05-patient-form.png`: existing registration form, unchanged fields and save action.
- `06-calendar.png`: existing calendar, status actions, reschedule and care links.
- `07-empty-dashboard.png`: actual zero counts and empty schedule.
- `08-partial-failure.png`: schedule, follow-up and lab failures; recall remains available.
- `09-inventory-overview.png`: inventory-only user without coordination requests.

Browser checks also covered 320px and 1024px viewport widths. The dashboard had no
horizontal page overflow at 320, 390, 1024, and 1440px. The drawer opens and closes after
selection. Patient list, registration, and calendar navigation were checked; no writes were
submitted. The final dashboard/mobile checks emitted no browser errors or warnings.

## Click-through with the normal local stack

1. Start the existing API and web app as documented in README.md; sign in normally.
2. Open `/`: the date uses the clinic timezone and cards use live authorized responses.
3. Follow the appointment card to the calendar and a patient name to patient detail.
4. Follow the due and lab cards to their existing queues.
5. Use Find patient and Register patient to reach the unchanged workflows.
6. At a mobile width, open the menu, choose a destination, and verify the drawer closes.
7. Sign in as an inventory-only user and open `/` for inventory and visit-type rule links.

Business-state mutations remain covered by the existing component tests. Backend database
integration tests were not run against a configured PostgreSQL database in this session.
