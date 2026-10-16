# Open items

- **Appointment status undo.** A mistaken arrived, no-show, start or complete cannot be reversed
  from the calendar. Care sessions do not undo the visit either. Next action: a small slice
  if the desk needs it.
- **Care item status undo.** A mistaken start, complete or cancel on a care item cannot be
  reversed. Next action: same as appointment status undo, or a paired slice if the desk asks.
- **`get_or_create_clinic` matches by display name.** The name is not unique, not trimmed,
  and case-sensitive. Fine for one dev clinic; fragile for multi-clinic provisioning. Next
  action: decide in a later slice whether `create-user` should take `--clinic-id` or a
  stable slug instead.
- **Patient “registered” date on detail.** The UI shows the `YYYY-MM-DD` prefix of
  `created_at` (UTC), not the clinic timezone. Next action: revisit when front desk reports
  wrong calendar day near midnight.
- **`patient_id` on upcoming appointments.** `GET /patients/{id}/appointments` includes
  `patient_id` on each row though the S1.3 brief did not require it. Next action: remove in
  a small API tidy-up if you want the response minimal, or keep for shared appointment shapes.
