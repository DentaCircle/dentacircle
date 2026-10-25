# S4.1 proof: inventory items

Taken at commit `0360c56` on `slice/S4.1-inventory-items`.
Real app: API on :8000, web on :3000 (`next start` of this commit), local Postgres, synthetic data only.
Clinic: Synthetic Clinic. Staff: Synthetic Stores (`s41.inventory@x.test`, inventory_admin), Synthetic Clinician (`s41.clinician@x.test`), Synthetic Desk (`s41.desk@x.test`, receptionist). The password is the synthetic one in `apps/api/tests/patient_harness.py`.

The Next.js dev server's hot-reload socket failed (`ERR_INVALID_HTTP_RESPONSE`) and its client components did not hydrate. These shots are from `next start` of the same commit. That client did hydrate: the forms were submitted and the notices, validation, and role checks below are from that run. This production click-through is the accepted check for the slice.

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-inventory-list.png` | Consumables and Medicines. Gloves M (box) and Medicine A (tablets). Inventory is the current nav item. | Sign in as Synthetic Stores. Add both categories and both items. The "Category renamed." line is from renaming the first category back to Consumables before this shot. |
| `02-add-item-validation.png` | "Enter a name.", "Choose a category." and "Enter a unit." | On that page, press Add item with the name, category and unit empty. |
| `03-categories.png` | "Category renamed." Consumables is now Clinic supplies (1). The active list shows Medicine A only, because Gloves M is inactive by this point. The count includes that inactive item. | Rename Consumables to Clinic supplies. |
| `04-inactive-empty.png` | Inactive filter, "No inventory items yet." The add form is empty. | Open Inactive before any item is deactivated. |
| `05-batches.png` | Gloves M, LOT-A 1 Oct 2026 with Expired, LOT-B 1 Jun 2027, and an empty Add batch form. | Open Gloves M. Add the two batches. This shot is after Reactivate, so the notice says "Item reactivated." |
| `06-duplicate-batch.png` | "That batch number is already in use." The typed value `lot-a` stays in the field. The message does not repeat a server copy of it. | Add batch `lot-a` again. |
| `07-inactive-item.png` | "Item deactivated." Status Inactive. "This item is inactive. New batches cannot be added." Existing batches can still be edited. No Add batch button. | Deactivate, then Confirm deactivation. |
| `08-clinician-readonly.png` | Synthetic Clinician sees Gloves M and both batches. No edit form, no Deactivate, no Add batch. | Sign in as Synthetic Clinician and open Gloves M. |
| `09-receptionist.png` | "You do not have access." | Sign in as Synthetic Desk and open `/inventory`. |

## Sample API calls

Signed in as Synthetic Stores unless a call says otherwise. Names are sent with surrounding spaces and stored trimmed.

```
POST /inventory/categories
{"name":" Wipes "}

HTTP 201
{"id":"1e13247d-ce09-463a-8ec7-7876a845e06c","name":"Wipes","item_count":0}
```

```
POST /inventory/items
{"name":" Alcohol wipes ","category_id":"1e13247d-ce09-463a-8ec7-7876a845e06c","unit":" pack ","low_stock_threshold":2}

HTTP 201
{"id":"8479b9ea-6286-48b5-809b-16bffde93071","name":"Alcohol wipes","category":{"id":"1e13247d-ce09-463a-8ec7-7876a845e06c","name":"Wipes"},"unit":"pack","low_stock_threshold":2,"status":"active","batch_count":0}
```

```
POST /inventory/items/8479b9ea-6286-48b5-809b-16bffde93071/batches
{"batch_number":" lot-9 ","expiry_on":"2026-10-01"}

HTTP 201
{"id":"fc58c00c-fb90-47f2-8a9e-5a69801deec7","batch_number":"lot-9","expiry_on":"2026-10-01","expired":true,"created_at":"2026-10-25T13:21:02.496459+05:30"}
```

```
GET /inventory/items?status=active

HTTP 200
{"items":[{"id":"8479b9ea-6286-48b5-809b-16bffde93071","name":"Alcohol wipes","category":{"id":"1e13247d-ce09-463a-8ec7-7876a845e06c","name":"Wipes"},"unit":"pack","low_stock_threshold":2,"status":"active","batch_count":1},{"id":"2f9f561a-191c-4f57-b8a7-877f645d0459","name":"Medicine A","category":{"id":"c21f8687-7b82-4e78-ac8c-59c2cb75a236","name":"Medicines"},"unit":"tablets","low_stock_threshold":0,"status":"active","batch_count":0}],"total":2,"page":1,"page_size":20}
```

```
POST /inventory/items/8479b9ea-6286-48b5-809b-16bffde93071/batches
{"batch_number":"LOT-9","expiry_on":"2027-01-01"}

HTTP 409
{"error":{"code":"duplicate_batch","message":"That batch number is already in use.","request_id":"d7a925d4-642a-405c-9600-26f4cd695100"}}
```

```
GET /inventory/items/11111111-1111-1111-1111-111111111111

HTTP 404
{"error":{"code":"not_found","message":"Not Found","request_id":"8eaad215-bf64-41b4-9907-3956bf1f0e44"}}
```

A clinician `POST /inventory/categories` returns 403 `forbidden`, "You do not have access." No session on `GET /inventory/items` returns 401 `unauthenticated`, "Sign in required."
