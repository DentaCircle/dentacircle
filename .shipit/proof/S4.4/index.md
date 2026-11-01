# S4.4 proof

All four screenshots were captured on 2026-11-01 from the production build at source tree commit `045c85a641a2e225739c1feba339e94f8aa362ef`, after merging the UI from PR #32. The real Next.js app used an isolated disposable PostgreSQL database and synthetic staff and inventory records. The browser viewport was 1440 × 1000; production mode removes the Next.js development overlay.

The synthetic clinic date is 1 Nov 2026. Synthetic gloves have a low-stock threshold of five, four units expired yesterday, two units expiring in 30 days, and three units expiring in 31 days. Total stock is nine and usable stock is five. Synthetic masks have no batches and are out of stock.

1. `01-attention-list.jpg` — As a clinician, open Inventory and select Needs attention. The new clinic workspace shell frames the full-width inventory table; gloves show low-stock, expired and expiring-soon badges, while masks show out of stock.
2. `02-filtered-empty.jpg` — Select Expired and search for `nomatch`. The combined filters retain the current selection and show the filtered empty state.
3. `03-admin-detail.jpg` — As clinic admin, open Synthetic gloves. The full detail shows both stock totals, item alerts, expired and expiring-soon batches, and existing write controls.
4. `04-clinician-detail.jpg` — Open the same item as a clinician. The same totals, alerts and batches are visible without write controls.

`api-responses.json` contains the clinician's current synthetic responses for Needs attention, Expired and Out of stock.
