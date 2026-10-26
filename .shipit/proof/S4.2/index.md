# S4.2 proof: restock and transactions

Taken at commit `8e0f34a` on `slice/S4.2-restock-and-transactions`.
Real app: API on :8000 (`COOKIE_SECURE=false`), web on :3000 (`next start` of this commit), local Postgres at migration `0019_inventory_transactions`, synthetic data only.
Clinic: S42 Synthetic Clinic. Staff: Synthetic Stores (`s42.inventory@x.test`, inventory_admin) and Synthetic Clinician (`s42.clinician@x.test`). The password is the synthetic one in `apps/api/tests/patient_harness.py`.

The Next.js dev server's hot-reload socket failed on the previous slice, so these shots are from `next start` of this commit. The forms were submitted in that client: the notices, the validation text, and the role checks below are from that run.

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-item-stock-and-history.png` | Gloves M, Stock 45, LOT-1 quantity 45, history newest first (adjustment −5 Damaged, then restock +50). | Sign in as Synthetic Stores. Add category Consumables, item Gloves M (box), batch LOT-1. Add stock 50, then adjust −5 with reason Damaged. |
| `02-add-stock-validation.png` | "Enter a whole number from 1 to 1,000,000." Stock is still 0 and history says "No stock movements yet." | On the new batch, press Add stock with Quantity empty. |
| `03-insufficient-stock.png` | "There is not enough stock." The typed −100 and Damaged stay in the form. History is unchanged. | After the +50 and −5, adjust −100 with reason Damaged. |
| `04-inactive-adjust-only.png` | "Item deactivated." Status Inactive. No Add stock button. Adjust is still there. History is still visible. | Deactivate, then Confirm deactivation. |
| `05-clinician-read-only.png` | Synthetic Clinician sees Stock 45, LOT-1 quantity 45, and the same history. No edit form, no Add stock, no Adjust. | Sign out. Sign in as Synthetic Clinician. Open Inventory, Inactive, Gloves M. |
| `06-list-stock-column.png` | The list has a Stock column. Gloves M shows 45, with no low-stock styling. | Open Inventory after the +50 and −5, before deactivating. |

## Sample API calls

Signed in as Synthetic Stores unless a call says otherwise. These calls were made after the screenshots, on the same item and batch. The item was reactivated for the restock sample and set inactive again afterwards. The live history therefore has two more rows than the screenshots.

```
POST /inventory/batches/03e47648-9093-4cf0-86a4-78593384075a/restock
{"quantity":2}

HTTP 201
{"id":"3e766f96-28e5-43ad-a168-845eab7de328","type":"restock","reason":null,"quantity_change":2,"batch":{"id":"03e47648-9093-4cf0-86a4-78593384075a","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T15:20:15.415902+05:30"}
```

```
POST /inventory/batches/03e47648-9093-4cf0-86a4-78593384075a/adjustments
{"quantity_change":-1,"reason":"damaged"}

HTTP 201
{"id":"641a3bfa-4a26-4c62-8db6-7aec540d017e","type":"adjustment","reason":"damaged","quantity_change":-1,"batch":{"id":"03e47648-9093-4cf0-86a4-78593384075a","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T15:19:39.489831+05:30"}
```

```
GET /inventory/items/fb23544f-55af-497f-aa90-2157c214892e/transactions?page=1&page_size=20

HTTP 200
Signed in as Synthetic Clinician.
{"items":[{"id":"641a3bfa-4a26-4c62-8db6-7aec540d017e","type":"adjustment","reason":"damaged","quantity_change":-1,"batch":{"id":"03e47648-9093-4cf0-86a4-78593384075a","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T15:19:39.489831+05:30"},{"id":"751cdce5-11d1-4875-883a-b9a3184b67ac","type":"adjustment","reason":"damaged","quantity_change":-5,"batch":{"id":"03e47648-9093-4cf0-86a4-78593384075a","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T15:16:07.958078+05:30"},{"id":"6b41c5e4-54c0-4152-9d0d-4ced80bc63c7","type":"restock","reason":null,"quantity_change":50,"batch":{"id":"03e47648-9093-4cf0-86a4-78593384075a","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T15:16:07.840313+05:30"}],"total":3,"page":1,"page_size":20}
```

The history sample above was taken after the −1 adjustment and before the later restock of 2, so `total` is 3.

```
POST /inventory/batches/03e47648-9093-4cf0-86a4-78593384075a/adjustments
{"quantity_change":-1000000,"reason":"expired"}

HTTP 409
{"error":{"code":"insufficient_stock","message":"There is not enough stock.","request_id":"26e545bc-ef4f-4381-9c5f-8c33c93840d8"}}
```

```
POST /inventory/batches/00000000-0000-4000-8000-000000000099/restock
{"quantity":1}

HTTP 404
{"error":{"code":"not_found","message":"Not Found","request_id":"2fde9ce9-eb62-4908-a30f-77b089a8086f"}}
```
