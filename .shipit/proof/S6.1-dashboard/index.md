# S6.1 visual proof

All records and accounts are synthetic. Screenshots show application commit
`abd118d2a1290a127e24c8c182cd81f477e2ad81`; the subsequent commit adds an API test only.

1. `01-populated-narrow.png` — sign in as the synthetic coordinator after creating three
   visits, one due follow-up, one open lab item and one due reminder through the API.
2. `02-empty.png` — sign in as the coordinator before creating records; the day and
   queues are empty.
3. `03-unavailable.png` — route the local app through a temporary proxy returning 503
   only for `/reminders`; reload the populated dashboard.
4. `04-inventory.png` — sign in as the synthetic inventory-only user.

The required populated desktop screenshot is missing: the available browser screenshot
capture clips the right side when a desktop viewport is set. Attempts at 1280 and 1440
pixels produced clipped images, so neither is presented as complete proof.
