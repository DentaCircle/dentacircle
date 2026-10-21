# S2.7 proof

Code these shots were taken against: `a2f15c0` (Write the M3 click-through and link it from the README).

Clinic: Synthetic Clinic. Staff: Synthetic Clinician (`s27.clinician@x.test`), Synthetic Desk (`s27.desk@x.test`). Patient: Sample Ada, phone 9000000091, display id P-0009. Dates are clinic-local Asia/Kolkata, Wednesday 21 Oct 2026. No clinical notes. The password is the one set with `make create-user`.

Every visit was booked for today, so Arrived was allowed with no database edit. The follow-up date on the first Scaling visit was set to today, so Due shows the row at once.

1. `01-due.png` — Signed in as Synthetic Desk. Follow-ups, Due. Sample Ada, due 21 Oct 2026, Due today, Scheduled, with Mark contacted, Book visit and Cancel follow-up. The right edge repeats a sliver of the same page. That is the capture surface, not a second queue.
2. `02-contacted.png` — Same view after Mark contacted. The notice is "Marked contacted." The row stays Due today and is now Contacted. Same capture sliver on the right.
3. `03-care.png` — Ada's Care page after Book visit. Follow-up due 21 Oct 2026, Booked. Sample plan is Open. Scaling is Completed. Root canal is Started.
4. `04-recalls.png` — Recalls, All open, before the recall was contacted. Recall type Scaling, due 21 Apr 2027, Upcoming, Scheduled. Phone and last visit are off this frame so the type, due date and status fit.
5. `05-timeline.png` — After the full story, signed in as Synthetic Clinician. Timeline page 1, newest first: Recall created (Scaling, due 21 Apr 2027), Recall completed, Follow-up updated due 28 Oct 2026, then the last Scaling visit. The list continues on later pages.
6. `06-calendar.png` — Calendar, Wed 21 Oct. Three Completed rows for Ada: Scaling 10:00, Consultation 11:00, Scaling 12:00. All with Synthetic Clinician.
