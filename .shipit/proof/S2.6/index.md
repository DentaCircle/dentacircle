# S2.6 proof

Code these shots were taken against: `4875c6c` (Show the patient timeline grouped by clinic day).

Clinic: Timeline Clinic. Staff: Sample Clinician (`s26.clinician@x.test`), Sample Desk (`s26.desk@x.test`), Sample Stores (`s26.stores@x.test`). Patients: Sample Ada P-0001, Sample Bea P-0002. Dates are clinic-local Asia/Kolkata. No clinical notes.

Ada's loop was written through the API. The Scaling visit is 10:00 and the Consultation booked from the follow-up is 11:00, both on Tue 20 Oct. Those visits were booked on a later open slot and then placed on today, because arrived is only allowed on the visit's clinic-local day. The oldest eight events had `occurred_at` set to Mon 19 Oct 10:00 so one screen shows two days. Bea's registration event was removed so the empty screen can be shown; a patient registered after this slice has a registration event.

1. `01-loop.png` — Signed in as Sample Clinician. Ada's timeline, page 1. Tue 20 Oct is newest: follow-up, the Consultation visit, the Scaling recall, the care session. Mon 19 Oct is below it.
2. `02-empty.png` — Sample Bea. "Nothing has happened for this patient yet."
3. `03-no-access.png` — Signed in as Sample Stores. "You do not have access."
4. `04-patient-button.png` — Sample Ada's page. Timeline sits next to Care.
5. `05-page-2.png` — Page 2. The remaining Mon 19 Oct rows, ending with Patient registered. Previous is the only page link.

The calendar day for 20 Oct shows both visits completed. The care page shows Scaling completed and a follow-up due 27 Oct.

## Sample

`GET /patients/d3f28243-13e4-47be-a5c5-3c9254b9ea99/timeline?page=1&page_size=20` as Sample Clinician.

`200`. The live page has 20 items and `"total": 24`. Four of those items:

```json
{
  "items": [
    {
      "id": "c2bcb745-8039-45db-bbeb-08f089c13d51",
      "kind": "follow_up_created",
      "occurred_at": "2026-10-20T23:15:18.237604+05:30",
      "actor": {
        "id": "30004bd7-3979-4713-a3b7-92b3457d4190",
        "name": "Sample Clinician"
      },
      "subject": {
        "due_on": "2026-10-27"
      }
    },
    {
      "id": "ad03713b-d767-453e-b3e6-dd406e071d01",
      "kind": "visit_completed",
      "occurred_at": "2026-10-20T23:15:18.237604+05:30",
      "actor": {
        "id": "30004bd7-3979-4713-a3b7-92b3457d4190",
        "name": "Sample Clinician"
      },
      "subject": {
        "appointment_id": "faf8e4ab-7537-43bb-82c9-03ad1e833e64",
        "type_name": "Consultation",
        "clinician_name": "Sample Clinician",
        "starts_at": "2026-10-20T11:00:00+05:30"
      }
    },
    {
      "id": "c8b9d1ad-f9eb-4a19-a132-352de2dca319",
      "kind": "recall_created",
      "occurred_at": "2026-10-20T23:15:18.168029+05:30",
      "actor": {
        "id": "30004bd7-3979-4713-a3b7-92b3457d4190",
        "name": "Sample Clinician"
      },
      "subject": {
        "due_on": "2027-04-20",
        "type_name": "Scaling"
      }
    },
    {
      "id": "09190546-9339-4ba0-922e-b6d02f8c0b51",
      "kind": "care_session_recorded",
      "occurred_at": "2026-10-20T23:15:18.151026+05:30",
      "actor": {
        "id": "30004bd7-3979-4713-a3b7-92b3457d4190",
        "name": "Sample Clinician"
      },
      "subject": {
        "care_session_id": "d281a93a-b86c-44fc-9541-bab4c3466c4c",
        "item_names": ["Scaling"]
      }
    }
  ],
  "total": 24,
  "page": 1,
  "page_size": 20
}
```
