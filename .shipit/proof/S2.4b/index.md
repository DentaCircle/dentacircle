# S2.4b proof

Code these shots were taken against: `9b2e454` (Add a cancel action on each follow-up row).

Clinic: Synthetic Clinic. Staff: Sample Desk (`s24.desk@x.test`), Sample Clinician (`s24.clinician@x.test`), Sample Stores (`s24.stores@x.test`). Patients: Sample Nia P-0006, Sample Pia P-0007, Sample Rae P-0008. Older rows for Sample Quinn, Sample Tia and Sample Uma were already on the queue. Dates are clinic-local Asia/Kolkata on Tue 20 Oct 2026. No clinical notes.

1. `01-all-open.png` — Signed in as Sample Desk. All open, before Nia's visit is completed. Nia P-0006 is Booked, due 20 Oct. Pia is also Booked. Rae is Scheduled. Every row has Cancel follow-up.
2. `02-visit-completed.png` — Signed in as Sample Clinician, day view, that clinician only. Nia's 17:15 visit was marked arrived, started, then completed with no follow-up date. The page says "Marked completed." The visit badge is Completed.
3. `03-queue-after-complete.png` — All open after that. Nia's booked row is gone. A new Scheduled row for Nia is due 27 Oct (completion day plus 7). She still has an open care item.
4. `04-due-contacted.png` — Pia's booked visit (Wed 21 Oct, 09:00) was cancelled on the calendar. Due view then shows Pia as Contacted, due 20 Oct, with Book visit. Quinn and Tia stay Booked, so they are not in Due.
5. `05-cancel-confirm.png` — Cancel follow-up on Rae. The question is "Cancel this follow-up? This cannot be undone." with Yes, cancel and Keep.
6. `06-follow-up-cancelled.png` — After Yes, cancel. Rae is gone. The page says "Follow-up cancelled." Pia is still Contacted.
7. `07-inventory-admin.png` — Signed in as Sample Stores. The page says "You do not have access."

## Sample cancel

`POST /follow-ups/c4f491ef-7318-4886-90a0-1bd98aec98a7/cancel` with no body, as Sample Desk, on Pia's contacted row after shot 6.

`204` and an empty body.

The same request again:

```json
{
  "error": {
    "code": "invalid_status",
    "message": "This follow-up has already changed.",
    "request_id": "261c3df2-c14c-4e47-89a2-c678435d3fb7"
  }
}
```

## Sample list after the new follow-up

`GET /follow-ups?view=all` after shot 3, still before Pia's row was cancelled from the queue. Nia is the new scheduled row.

```json
{
  "items": [
    {
      "id": "9b0d1ea0-894a-48af-bbdf-d1f06d66e7ce",
      "status": "scheduled",
      "due_on": "2026-10-27",
      "timing": "upcoming",
      "patient": {
        "id": "fa4cd6e6-08c9-4821-8c4d-e9587ecac50d",
        "display_id": "P-0006",
        "full_name": "Sample Nia",
        "phone": "9800002401"
      }
    }
  ]
}
```

The list also still contained Quinn, Tia, Pia and Uma. Nia's item is the one this slice added.
