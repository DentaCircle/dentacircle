# S4.4 proof

All screenshots use the real app at commit `bc33b52`, with an isolated synthetic clinic and synthetic staff. The sample item has four expired units, two units expiring in 30 days, and three units expiring in 31 days; its threshold is five.

1. `01-attention-list.png` — Sign in as the synthetic clinician, open Inventory and select Needs attention. The gloves have low-stock, expired and expiring-soon badges; masks with no batches are out of stock.
2. `02-filtered-empty.png` — Select Expired and search for `nomatch`; the combined filters return no items.
3. `03-admin-detail.png` — Sign in as the synthetic clinic admin and open Synthetic gloves. The totals, alerts and write controls are visible.
4. `04-clinician-detail.png` — Sign in as the synthetic clinician and open the same item. The mixed batches and both totals are visible without write controls.

`api-responses.json` contains the synthetic clinician's responses to the attention, expired and out-of-stock filters at the same commit.
