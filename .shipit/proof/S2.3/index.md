# S2.3 proof

Code these shots were taken against: `42ab324` (Report a stale completion before the follow-up date, and publish the new routes in the API contract).

Clinic: Synthetic Clinic. Staff: Sample Clinician (`s23.clinician@x.test`), Sample Desk (`s23.desk@x.test`), Sample Stores (`s23.stores@x.test`). Patients: Sample Quinn P-0001, Sample Rhea P-0002, Sample Sia P-0003, Sample Tia P-0004, Sample Uma P-0005. Visits on Tue 20 Oct, Asia/Kolkata. No clinical notes.

1. `01-create-form.png` — Signed in as Sample Clinician. Quinn has no follow-up. Care shows Follow-up date and Create follow-up.
2. `02-follow-up-created.png` — Same page after Create follow-up for 27 Oct 2026. The line is "Follow-up due 27 Oct 2026" with Scheduled. The form is gone.
3. `03-past-date.png` — Rhea, date 19 Oct 2026. The page says "Choose a date from today through the next year." No follow-up was created.
4. `04-receptionist.png` — Signed in as Sample Desk. Sia has no follow-up. The same create form is shown. There is no new-plan control.
5. `05-calendar-confirm.png` — Sample Clinician, day view 20 Oct, filtered to Sample Clinician. Tia's 16:30 visit is in progress. Complete opened "Mark as completed?" with Follow-up date set to 28 Oct 2026.
6. `06-complete-no-open-items.png` — Tia's care page after Yes. Scaling is Completed and the plan is Finished. "Follow-up due 28 Oct 2026", Scheduled. No create form.
7. `07-date-replaced.png` — Uma already had one open follow-up due 27 Oct 2026 and Scaling still planned. Completing the 17:00 visit with 3 Nov 2026 left one line, "Follow-up due 3 Nov 2026", Scheduled. The plan stays Open.
8. `08-inventory-admin.png` — Signed in as Sample Stores, Quinn's care URL. The page says "You do not have access."

## Sample create

`POST /patients/a28f1934-861e-4a9f-b241-53bd38ae8804/follow-up` from the care form in shot 2.

```json
{ "due_on": "2026-10-27" }
```

`GET /patients/a28f1934-861e-4a9f-b241-53bd38ae8804/follow-up` after that create. `appointment_id` is null.

```json
{
  "follow_up": {
    "id": "6ef7dbb3-95f2-4a7e-a8d1-532019e396aa",
    "patient_id": "a28f1934-861e-4a9f-b241-53bd38ae8804",
    "appointment_id": null,
    "status": "scheduled",
    "due_on": "2026-10-27",
    "created_at": "2026-10-20T14:08:05.235729+05:30"
  }
}
```

## Sample completion date

`POST /appointments/398d1dee-fb40-4a6b-ad2b-8508f12d7cf0/status` from Yes in shot 5. Tia had no open care item.

```json
{ "status": "completed", "follow_up_due_on": "2026-10-28" }
```

`GET /patients/fd12d88f-9951-4a96-9547-473354cf02ca/follow-up` after that completion.

```json
{
  "follow_up": {
    "id": "5d5ec166-3aaf-44a0-ac8a-683d4ec17e8d",
    "patient_id": "fd12d88f-9951-4a96-9547-473354cf02ca",
    "appointment_id": "398d1dee-fb40-4a6b-ad2b-8508f12d7cf0",
    "status": "scheduled",
    "due_on": "2026-10-28",
    "created_at": "2026-10-20T14:10:43.622768+05:30"
  }
}
```

Uma's open row was `e2d07bf7-4d27-4b27-9da9-6718cca779e6`, due `2026-10-27`, `appointment_id` null. After `POST /appointments/a7af860e-735a-4f8b-abc9-86e47ee37323/status` with `{ "status": "completed", "follow_up_due_on": "2026-11-03" }`, the same id reads:

```json
{
  "follow_up": {
    "id": "e2d07bf7-4d27-4b27-9da9-6718cca779e6",
    "patient_id": "0653ddad-e2fc-4bf4-9447-30db53eaa553",
    "appointment_id": "a7af860e-735a-4f8b-abc9-86e47ee37323",
    "status": "scheduled",
    "due_on": "2026-11-03",
    "created_at": "2026-10-20T14:06:26.206627+05:30"
  }
}
```
