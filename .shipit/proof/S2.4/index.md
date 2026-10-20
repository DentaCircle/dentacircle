# S2.4 proof

Code these shots were taken against: `633d72f` (Add the coordinator queue page and book the next visit from a follow-up row).

Clinic: Synthetic Clinic. Staff: Sample Desk (`s23.desk@x.test`), Sample Stores (`s23.stores@x.test`). Patients: Sample Quinn P-0001, Sample Tia P-0004, Sample Uma P-0005. Dates are clinic-local Asia/Kolkata on Tue 20 Oct 2026. No clinical notes.

1. `01-all-open.png` — Signed in as Sample Desk. All open: Quinn overdue 18 Oct Scheduled, Tia due today 20 Oct Scheduled, Uma upcoming 3 Nov Scheduled. Follow-ups is in the nav.
2. `02-due.png` — Due view. Quinn and Tia only. Uma is hidden.
3. `03-contacted.png` — After Mark contacted on Quinn. The page says "Marked contacted." Quinn is Contacted; the button is gone. Book visit remains.
4. `04-book-page.png` — Book visit from Tia's row. Type Consultation, clinician Sample Clinician, date 20 Oct 2026, slots 16:00 and 17:30 (later morning slots had already passed).
5. `05-visit-booked.png` — After booking Tia at 16:00. All open says "Visit booked." Tia is Booked with no actions. Quinn still Contacted.
6. `06-empty.png` — Due view after Quinn was also booked. "No follow-ups are due." Uma is upcoming, so she stays off Due.
7. `07-inventory-admin.png` — Signed in as Sample Stores. The page says "You do not have access."

## Sample list

`GET /follow-ups` (Due, default) after shots 5 and 6, still as Sample Desk.

```json
{ "items": [], "total": 0, "page": 1, "page_size": 20 }
```

`GET /follow-ups?view=all` after Tia and Quinn were booked, Uma still scheduled.

```json
{
  "items": [
    {
      "id": "6ef7dbb3-95f2-4a7e-a8d1-532019e396aa",
      "status": "booked",
      "due_on": "2026-10-18",
      "timing": "overdue",
      "patient": {
        "id": "a28f1934-861e-4a9f-b241-53bd38ae8804",
        "display_id": "P-0001",
        "full_name": "Sample Quinn",
        "phone": "9800002301"
      }
    },
    {
      "id": "5d5ec166-3aaf-44a0-ac8a-683d4ec17e8d",
      "status": "booked",
      "due_on": "2026-10-20",
      "timing": "due_today",
      "patient": {
        "id": "fd12d88f-9951-4a96-9547-473354cf02ca",
        "display_id": "P-0004",
        "full_name": "Sample Tia",
        "phone": "9800002304"
      }
    },
    {
      "id": "e2d07bf7-4d27-4b27-9da9-6718cca779e6",
      "status": "scheduled",
      "due_on": "2026-11-03",
      "timing": "upcoming",
      "patient": {
        "id": "0653ddad-e2fc-4bf4-9447-30db53eaa553",
        "display_id": "P-0005",
        "full_name": "Sample Uma",
        "phone": "9800002305"
      }
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20
}
```

## Sample contacted

`POST /follow-ups/e2d07bf7-4d27-4b27-9da9-6718cca779e6/contacted` with no body, after the shots, on Uma.

```json
{
  "id": "e2d07bf7-4d27-4b27-9da9-6718cca779e6",
  "status": "contacted",
  "due_on": "2026-11-03",
  "timing": "upcoming",
  "patient": {
    "id": "0653ddad-e2fc-4bf4-9447-30db53eaa553",
    "display_id": "P-0005",
    "full_name": "Sample Uma",
    "phone": "9800002305"
  }
}
```

## Sample book

`POST /follow-ups/5d5ec166-3aaf-44a0-ac8a-683d4ec17e8d/book` from shot 5. 201.

```json
{
  "clinician_id": "dae9bbe0-eb5f-48c8-8e58-ab5ff3d38550",
  "appointment_type_id": "80f73de1-bb7c-4042-9075-b9a541f5eb2a",
  "starts_at": "2026-10-20T16:00:00+05:30"
}
```

The created visit, `GET /appointments/aabe4da4-8167-4d98-9ac5-62583382e6de`:

```json
{
  "id": "aabe4da4-8167-4d98-9ac5-62583382e6de",
  "starts_at": "2026-10-20T16:00:00+05:30",
  "ends_at": "2026-10-20T16:30:00+05:30",
  "status": "scheduled",
  "patient": {
    "id": "fd12d88f-9951-4a96-9547-473354cf02ca",
    "full_name": "Sample Tia",
    "display_id": "P-0004"
  },
  "clinician": {
    "id": "dae9bbe0-eb5f-48c8-8e58-ab5ff3d38550",
    "full_name": "Sample Clinician"
  },
  "appointment_type": {
    "id": "80f73de1-bb7c-4042-9075-b9a541f5eb2a",
    "name": "Consultation"
  }
}
```

Tia's follow-up `booked_appointment_id` is that visit. Quinn's booked visit is `659ff621-5321-450e-9d56-0aa1e7f970f6` at 17:30 the same day.
