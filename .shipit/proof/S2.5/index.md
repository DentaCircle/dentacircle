# S2.5 proof

Code these shots were taken against: `0dadcc8` (Show recalls on their own page with the same queue actions as follow-ups).

Clinic: Recall Clinic. Staff: Sample Desk (`s25.desk@x.test`), Sample Clinician (`s25.clinician@x.test`), Sample Stores (`s25.stores@x.test`). Empty clinic: Empty Recall Clinic, Sample Empty (`s25.empty@x.test`). Patients: Sample Ada P-0001, Sample Bea P-0002, Sample Cyd P-0003, Sample Dee P-0004. Dates are clinic-local Asia/Kolkata on Tue 20 Oct 2026. No clinical notes.

The four recalls come from completed Scaling visits on 21 Oct 2026. Due dates were then set to 19 Oct, 20 Oct, 27 Oct and 3 Nov so the page can show Overdue, Due today and Upcoming on the same day. Bea was marked contacted. Dee was booked onto 22 Oct 10:00.

1. `01-all-open.png` — Signed in as Sample Desk. All open. Ada is Overdue and Scheduled, with Mark contacted, Book visit and Cancel recall. Bea is Due today and Contacted, with Book visit and Cancel recall. Cyd is Upcoming and Scheduled. Dee is Upcoming and Booked, with Cancel recall only.
2. `02-due.png` — Due view. Ada and Bea only. Cyd's future row and Dee's booked row are absent.
3. `03-empty.png` — Signed in as Sample Empty. "No recalls are due."
4. `04-no-access.png` — Signed in as Sample Stores. "You do not have access." The Due and All open switch is hidden.
5. `05-follow-ups.png` — Signed in as Sample Desk, before any later action. Follow-ups shows Ada's follow-up, due 20 Oct, with Cancel follow-up. Bea, Cyd and Dee are not on this list. The recall columns are not on this page.
6. `06-booked-row.png` — Dee's row on All open. Status Booked. Cancel recall. No Mark contacted and no Book visit.

After these shots, Ada was marked contacted through the same request the button sends. A reload showed "Marked contacted." and Ada no longer had Mark contacted. The book page for Bea's recall opened with type, clinician and date. Cyd was later booked through the API for the sample below, so a fresh All open now shows her as Booked too. The images above were taken first.

## Sample list

`GET /recalls?view=due` as Sample Desk, after Ada had been marked contacted. Cyd and Dee are not in this list.

```json
{
  "items": [
    {
      "id": "71788e02-75a7-46f2-bfa1-bd64b86b0272",
      "status": "contacted",
      "due_on": "2026-10-19",
      "timing": "overdue",
      "last_visit_on": "2026-10-21",
      "recall_type": {
        "id": "901980e3-89d5-4f51-8200-cd490412487b",
        "name": "Scaling"
      },
      "patient": {
        "id": "6266bf79-6974-4845-99f6-695bd7ed8a72",
        "display_id": "P-0001",
        "full_name": "Sample Ada",
            "phone": "9800002501"
            }
        },
        {
            "id": "c2e450f1-d045-4b1b-961f-d9e2d81950bf",
            "status": "contacted",
            "due_on": "2026-10-20",
            "timing": "due_today",
            "last_visit_on": "2026-10-21",
            "recall_type": {
                "id": "901980e3-89d5-4f51-8200-cd490412487b",
                "name": "Scaling"
            },
            "patient": {
                "id": "9d5a8bc0-e9c0-42ea-9040-2e3590a185c8",
                "display_id": "P-0002",
                "full_name": "Sample Bea",
                "phone": "9800002502"
            }
        }
    ],
    "total": 2,
  "page": 1,
  "page_size": 20
}
```

## Sample book

`POST /recalls/ef34c888-0691-4afb-991e-01cecd621afc/book` as Sample Desk, on Cyd's scheduled recall.

```json
{
  "clinician_id": "7dbcf4ac-ce0a-4f6b-8b23-d5f001cb10a6",
  "appointment_type_id": "901980e3-89d5-4f51-8200-cd490412487b",
  "starts_at": "2026-10-22T12:00:00+05:30"
}
```

`201`

```json
{
  "id": "bcf458bd-cda2-471f-b8da-0c2adf6eaa99",
  "patient_id": "4635fc30-3c32-4348-a1cc-165e90c99e44",
  "starts_at": "2026-10-22T12:00:00+05:30",
  "ends_at": "2026-10-22T12:30:00+05:30",
  "status": "scheduled",
  "clinician": {
    "id": "7dbcf4ac-ce0a-4f6b-8b23-d5f001cb10a6",
    "full_name": "Sample Clinician"
  },
  "appointment_type": {
    "id": "901980e3-89d5-4f51-8200-cd490412487b",
    "name": "Scaling"
  }
}
```

## Sample appointment type update

`PUT /appointment-types/901980e3-89d5-4f51-8200-cd490412487b` as Sample Desk. Scaling stays at 6 months.

```json
{
  "name": "Scaling",
  "duration_minutes": 30,
  "is_active": true,
  "recall_after_months": 6
}
```

`200`

```json
{
  "id": "901980e3-89d5-4f51-8200-cd490412487b",
  "name": "Scaling",
  "duration_minutes": 30,
  "recall_after_months": 6,
  "effective_duration_minutes": 30,
  "is_active": true
}
```
