# S4.3 proof: procedure resource rules and consumption

Taken at commit `30125e4` on `slice/S4.3-procedure-resource-rules`.
Real app: API on :8000 (`COOKIE_SECURE=false`), web on :3000 (`next start` of this source), local Postgres at migration `0020_procedure_resource_rules`, synthetic data only.
Clinic: S43 Synthetic Clinic. Staff: Synthetic Stores (`s43.inventory@x.test`, inventory_admin), Synthetic Clinician (`s43.clinician@x.test`), Synthetic Admin (`s43.admin@x.test`, clinic_admin). Patient: Sample Lila, display id P-0002. The password is the synthetic one in `apps/api/tests/patient_harness.py`.

Monday hours on this clinic were extended to 21:00 so a visit could be booked after 18:00. That change is data, not code.

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-rules-on-a-type.png` | Scaling uses Gloves M, quantity 2, with Save and Remove. The other types say "No stock is used by this visit type." | Sign in as Synthetic Stores. Open Inventory, Visit type rules. On Scaling, choose Gloves M, quantity 2, Add rule. |
| `02-add-rule-validation.png` | Scaling still has no rule. Quantity 0 shows "Enter a whole number from 1 to 1,000." | On that same form, choose Gloves M, type 0, Add rule. This shot is from before the successful save. |
| `03-used-in-visit.png` | Gloves M stock 8. LOT-1 quantity 8. History shows Used in visit −2, then Restock +10. | As Synthetic Clinician, mark the 20:00 Scaling visit Arrived, then Start. Complete it (the status call is noted below). Open Inventory, Gloves M. |
| `04-clinician-read-only.png` | Synthetic Clinician sees Scaling, Gloves M, quantity 2. No Add rule, Save, or Remove. | Stay signed in as Synthetic Clinician. Open Visit type rules. |

The Used in visit row is a link. Following it opens `/calendar?view=day&date=2026-10-26`, the clinic day of that visit.

The in-browser "Yes" on Mark as completed was blocked by the review check. Arrived and Start were clicked in the app. Completion was then `POST /appointments/{id}/status` as Synthetic Clinician, the same call the button makes. Stock moved from 10 to 8, and the history shot is from the page after that.

## Sample API calls

Signed in as Synthetic Stores unless a call says otherwise.

```
PUT /appointment-types/60fdc7a3-d4fc-462e-ae47-c4b2a4ef8733/resource-rules/1be3b7f6-fff6-4c16-8077-753cebc89041
{"quantity":2}

HTTP 200
{"item_id":"1be3b7f6-fff6-4c16-8077-753cebc89041","item_name":"Gloves M","quantity":2}
```

```
POST /appointments/11132d4f-9842-4f03-9c31-4bf4c2a12c05/status
{"status":"completed"}

HTTP 200
Signed in as Synthetic Clinician. The response status is "completed" and the type is Scaling.
```

```
GET /inventory/items/1be3b7f6-fff6-4c16-8077-753cebc89041/transactions?page=1&page_size=20

HTTP 200
{"items":[{"id":"c6541f7d-d307-4eec-adfa-957b5e849f7a","type":"consumption","reason":null,"quantity_change":-2,"batch":{"id":"4b77f536-3e61-4c03-ad60-217e26e4a237","batch_number":"LOT-1"},"recorded_by":"Synthetic Clinician","created_at":"2026-10-26T21:33:40.549058+05:30","appointment_id":"11132d4f-9842-4f03-9c31-4bf4c2a12c05","visit_on":"2026-10-26"},{"id":"0ccba6bd-93a0-4c89-a728-71e192d4c19e","type":"restock","reason":null,"quantity_change":10,"batch":{"id":"4b77f536-3e61-4c03-ad60-217e26e4a237","batch_number":"LOT-1"},"recorded_by":"Synthetic Stores","created_at":"2026-10-26T19:48:26.940657+05:30","appointment_id":null,"visit_on":null}],"total":2,"page":1,"page_size":20}
```

```
PUT /appointment-types/60fdc7a3-d4fc-462e-ae47-c4b2a4ef8733/resource-rules/00000000-0000-4000-8000-000000000099
{"quantity":2}

HTTP 404
{"error":{"code":"not_found","message":"Not Found","request_id":"88bb7b9b-c28e-4d42-ab20-8ed1904281fb"}}
```

```
PUT /appointment-types/60fdc7a3-d4fc-462e-ae47-c4b2a4ef8733/resource-rules/63800a14-1f37-4ced-b5db-3e9dad97e7cc
{"quantity":1}

HTTP 409
{"error":{"code":"item_inactive","message":"This item is inactive.","request_id":"2e086855-d176-4b06-b1b1-220d3fe1a686"}}
```

The 409 item is Expired swabs, deactivated before the call. The body does not include the quantity.
