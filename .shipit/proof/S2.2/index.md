# S2.2 proof

Code these shots were taken against: `8543a0d` (Show the open follow-up on the care page). Recapture of the complete path is on the sealed branch.

Clinic: Synthetic Clinic. Staff: Sample Clinician (`s22.clinician@x.test`), Sample Desk (`s22.desk@x.test`), Sample Stores (`s22.stores@x.test`). Patients: Sample Nia, display P-0008, Scaling still planned; Sample Opal, Scaling completed. Visits on Sat 17 Oct, Asia/Kolkata. No clinical notes.

Signed in as Sample Clinician. The 17:00–17:30 visit was already in progress. On the calendar, Complete opened "Mark as completed?". Yes completed the visit (the calendar then said "Marked completed."). Care still shows one line, "Follow-up due 24 Oct 2026", Scheduled. That visit is `f63e3422-7912-4096-a85f-ede38072e3d4`. The open follow-up stayed one row, due date unchanged, and its visit link is that 17:00 visit.

1. `01-calendar-before-complete.png` — Day view for Sat 17 Oct, filtered to Sample Clinician. Sample Nia, P-0008, 17:00–17:30, In progress, with Complete.
2. `02-care-follow-up.png` — Nia's care page after Yes. "Follow-up due 24 Oct 2026" with Scheduled, above Scaling plan (Open) and Scaling (Planned).
3. `03-care-no-follow-up.png` — Opal's care page. Scaling is Completed and the plan is Finished. No follow-up line.
4. `04-second-visit-same-due.png` — Same care page after the later 17:00 visit was completed with Complete and Yes. Still one line, still "Follow-up due 24 Oct 2026", still Scheduled.
5. `05-receptionist.png` — Signed in as Sample Desk, same care page. The line and badge are shown. There is no Start, Complete, Cancel, Rename, or new-plan control.
6. `06-inventory-admin.png` — Signed in as Sample Stores. The page says "You do not have access."
7. `07-follow-up-load-failure.png` — The follow-up read was forced to fail, then restored. Plans still show, with "Follow-up could not be loaded."

## Sample read

`GET /patients/d6e82520-3995-4142-b05f-74724ba88c19/follow-up` after the 17:00 visit was completed in the browser.

```json
{
  "follow_up": {
    "id": "9acbd9d0-56ef-4757-b18f-6bcf00a831c5",
    "patient_id": "d6e82520-3995-4142-b05f-74724ba88c19",
    "appointment_id": "f63e3422-7912-4096-a85f-ede38072e3d4",
    "status": "scheduled",
    "due_on": "2026-10-24",
    "created_at": "2026-10-17T07:57:34.237206Z"
  }
}
```

`due_on` is the date `2026-10-24` with no time. The later completion did not change it.
