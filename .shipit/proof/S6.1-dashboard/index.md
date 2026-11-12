# S6.1 visual proof

All records and accounts are synthetic. Screenshots 1–4 show application commit
`abd118d2a1290a127e24c8c182cd81f477e2ad81`. Later commits do not change the app.

1. `01-populated-narrow.png` — sign in as the synthetic coordinator after creating three
   visits, one due follow-up, one open lab item and one due reminder through the API.
2. `02-empty.png` — sign in as the coordinator before creating records; the day and
   queues are empty.
3. `03-unavailable.png` — route the local app through a temporary proxy returning 503
   only for `/reminders`; reload the populated dashboard.
4. `04-inventory.png` — sign in as the synthetic inventory-only user.

5. `05-populated-desktop.png` — at commit `840a03d`, sign in as the synthetic
   coordinator in a desktop browser and open the populated dashboard. The reminder
   count is zero because its scheduled visit had already started at capture time.
