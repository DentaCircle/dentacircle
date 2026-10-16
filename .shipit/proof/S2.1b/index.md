# S2.1b proof

Code these shots were taken against: `2fbb068` (Reset the care session form after a stale save).

Clinic: Synthetic Clinic. Staff: Sample Clinician (`clinician@x.test`), Sample Desk (`receptionist@x.test`), Sample Stores (`inventory@x.test`). Patient: Sample Ada, display P-0007. Plans: Root canal plan (Root canal, visit 1 and Root canal, visit 2) and Scaling plan (Scaling). Visits on Sat 17 Oct, Asia/Kolkata: 10:00 arrived, 10:30 scheduled, 11:00 arrived. No clinical notes.

1. `01-calendar-link.png` — Signed in as Sample Clinician, day view for Sat 17 Oct. The 10:00 and 11:00 arrived rows have a Care session link. The 10:30 scheduled row does not.
2. `02-recording-form.png` — The 10:00 visit. Root canal plan and Scaling plan are both listed. Root canal, visit 1 is Started. Scaling is Completed. Root canal, visit 2 is left on No change. Save care session is enabled.
3. `03-confirm.png` — Save care session asks "Save care session? Completed items cannot be undone." with Yes and Keep.
4. `04-saved.png` — After Yes. "Care session saved." Recorded by Sample Clinician. Root canal, visit 1 is Started. Scaling is Completed. The visit badge is still Arrived.
5. `05-receptionist.png` — Signed in as Sample Desk, same visit. The recorded lines are shown. There is no form and no Save care session.
6. `06-scheduled.png` — The 10:30 scheduled visit, as Sample Clinician. The page says "No care session recorded."
7. `07-stale-item.png` — The 11:00 form was open, then Root canal, visit 2 was completed from the care page before Save. Yes reloaded the form with "A care item has already changed." Visit 2 is gone. Visit 1 is still open, and Save care session is disabled until a new choice.
8. `08-inventory-admin.png` — Signed in as Sample Stores. Opening the 10:00 care session page shows "You do not have access."
