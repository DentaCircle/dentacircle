# S1.5 proof

Code these shots were taken against: `9ac5e66` (Keep the conflict notice after the calendar reloads).
Shots 1 to 7 were taken on `8e16f9b`, before that notice fix. The fix only changes what a 409 does, so those captions still match.

Clinic: Synthetic Clinic, timezone Asia/Kolkata, 30 minute visits. Staff used only for these shots: Test Desk (receptionist), Test Clinician, Test Stock (inventory_admin). Patients: Test Patient One, Test Patient Two, Test Patient Three.

Thursday 15 Oct 2026 was already past 18:00, so the clinic was closed for new bookings. As clinic admin, Thursday's open interval was set to 09:00–22:00 through `PUT /clinic/day`, the visits below were booked, and the interval was put back to 09:00–18:00 (weekdays 0–5) after the last shot. No database edit.

Calendar filter for shots 1 to 6, 8 and 9: day view, 15 Oct 2026, clinician Test Clinician.

1. `01-scheduled-receptionist.png` — Signed in as Test Desk. A scheduled row shows Reschedule, Cancel, Arrived and No-show.
2. `02-arrived-receptionist.png` — Arrived on the 20:00 Test Patient Two visit. Notice "Marked arrived." The badge is Arrived and Start is not shown.
3. `03-clinician-start.png` — Signed out, signed in as Test Clinician, same calendar. The 20:00 row shows Start.
4. `04-complete-confirm.png` — Start, then Complete. Badge In progress, notice "Marked in progress.", and the question "Mark as completed?" with Yes and Keep.
5. `05-completed.png` — Yes. Notice "Marked completed." Badge Completed. That row has no actions.
6. `06-no-show-too-early.png` — No-show on the 21:00 Test Patient One visit, before 21:00. The question "Mark as no-show?" is up, and the page says "No-show can only be set after the start time." The "Marked completed." notice from shot 5 is still on the page.
7. `07-arrived-other-day.png` — Next day, Friday 16 Oct, 10:00 Test Patient Two. Arrived. The page says "Arrived can only be set on the day of the visit."
8. `08-no-show.png` and `08-rebook.png` — After 19:30, No-show on the 19:30 Test Patient One visit, then Yes. The row badge is No-show and the notice is "Marked no-show." The question "Mark as no-show?" with Yes and Keep was on that row before Yes; the saved frame is the result. `08-rebook.png` is Book appointment for Test Patient Two, Test Clinician, 15 Oct 2026. 19:30 is not listed: availability only offers a start that is still ahead, and the shot was taken at about 19:33. The completed 20:00 visit and the arrived 21:00 visit still block the times around them, so the first offered time is 20:30. The service test is what shows a new booking at the freed start succeeding while the clock is still before that start.
9. `09-stale-tab.png` — Two tabs on the same calendar. The second tab marked the 21:00 Test Patient One visit arrived. The first tab, still showing Arrived for that row, was clicked. It reloaded with "This appointment's status has already changed." and the row is Arrived with Start.
10. `10-inventory-admin.png` — Signed in as Test Stock. Opening `/calendar` shows "You do not have access."
