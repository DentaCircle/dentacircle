# S6.2 visual proof

All clinics, users and stock are synthetic. Application commit: `b446dda`.
The app used an isolated PostgreSQL database with the existing migrations applied.

1. `01-inventory.png` — sign in as inventory-only, add three synthetic items with empty, expiring and expired stock, and scroll to attention at narrow width.
2. `02-filter.png` — select Out of stock; the inventory page opens with the alert filter selected.
3. `03-inventory-desktop.png` — the same inventory-only account at desktop width, showing shortcuts and attention counts.
4. `04-coordination.png` — sign in as a clinic admin and scroll to the inventory section under the coordination metrics.
5. `05-empty.png` — sign in as inventory staff in a clinic without items and scroll to the four zero counts and all-clear message.
6. `06-reception.png` — sign in as receptionist and scroll to the dashboard footer; inventory attention is absent.
7. `07-partial-failure.png` — serve API reads through a local test proxy returning 503 only for `alert=expired`, then reload as clinic admin at narrow width. Other inventory counts remain available.
8. `08-filtered-rows.png` — from the out-of-stock count, scroll to the filtered synthetic items, including expired-only stock.
