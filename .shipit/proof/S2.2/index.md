# S2.2 proof

Code these shots were taken against: `8543a0d` (Show the open follow-up on the care page).

Clinic: Synthetic Clinic. Staff: Sample Clinician (`s22.clinician@x.test`), Sample Desk (`s22.desk@x.test`), Sample Stores (`s22.stores@x.test`). Patients: Sample Nia, display P-0008, Scaling still planned; Sample Opal, Scaling completed. Visits on Sat 17 Oct, Asia/Kolkata. No clinical notes.

The calendar Complete control did not submit from the browser, so Nia's 16:30 visit (`6608e7de-4fd2-4bf5-a7b3-7f24f423a0a2`) was completed with `POST /api/appointments/6608e7de-4fd2-4bf5-a7b3-7f24f423a0a2/status` from the signed-in page. The response stayed the calendar item and the status became `completed`. The second visit, 15:00 (`69198cee-7c33-47db-ae33-dce51218a149`), was completed through the service. One follow-up remained, due 2026-10-24, pointing at the 15:00 visit.

1. `01-calendar-before-complete.png` — Day view for Sat 17 Oct, filtered to Sample Clinician. Sample Nia, P-0008, Consultation, 16:30–17:00, In progress, with Complete and Care session.
2. `02-care-follow-up.png` — Nia's care page after that visit completed. "Follow-up due 24 Oct 2026" with Scheduled, above Scaling plan (Open) and Scaling (Planned).
3. `03-care-no-follow-up.png` — Opal's care page. Scaling is Completed and the plan is Finished. No follow-up line.
4. `04-second-visit-same-due.png` — After the 15:00 visit also completed. Still one line, still "Follow-up due 24 Oct 2026", still Scheduled.
5. `05-receptionist.png` — Signed in as Sample Desk, same care page. The line and badge are shown. There is no Start, Complete, Cancel, Rename, or new-plan control.
6. `06-inventory-admin.png` — Signed in as Sample Stores. The page says "You do not have access."
7. `07-follow-up-load-failure.png` — The follow-up read was forced to fail, then restored. Plans still show, with "Follow-up could not be loaded."

## Sample read

`GET /patients/d6e82520-3995-4142-b05f-74724ba88c19/follow-up` as Sample Desk.

```json
{
  "follow_up": {
    "id": "9acbd9d0-56ef-4757-b18f-6bcf00a831c5",
    "patient_id": "d6e82520-3995-4142-b05f-74724ba88c19",
    "appointment_id": "69198cee-7c33-47db-ae33-dce51218a149",
    "status": "scheduled",
    "due_on": "2026-10-24",
    "created_at": "2026-10-17T07:57:34.237206Z"
  }
}
```

`due_on` is the date `2026-10-24` with no time. That is the clinic-local completion date (17 Oct) plus 7 days.
