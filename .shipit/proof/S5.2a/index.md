# S5.2a proof

Application commit: `e66dd5274aaf03f03970ba6bd92c025058137999`. The proof app used a
disposable PostgreSQL database, synthetic staff and patient records, and a fake provider.
No real WhatsApp account, message, or patient data was used. `samples.json` contains
sanitized history and timeline responses from the running API; account and patient IDs are
omitted and the staff ID is replaced with a placeholder.

The following screenshots are **still missing**. The running pages were inspected, but
the computer-use browser could not save their image bytes to the proof folder: its browser
clipboard did not transfer images to Preview, and access to the Codex window is blocked.
The conversation view must be cropped to exclude the linked synthetic number.

1. `01-inbox.png`: sign in to the synthetic app, open Messages, and show the queued automatic
   reply in the inbox.
2. `02-conversation.png`: open Sample Patient's Messages and capture only the message list,
   showing the queued and unconfirmed automatic replies and the inbound patient messages;
   exclude the linked number above the list.
3. `03-timeline.png`: open the patient's Timeline and show the visit booked by “Patient via
   WhatsApp” alongside staff registration.

The proof server used `http://127.0.0.1:3100` and `http://127.0.0.1:8100`. The synthetic
login is `proof@example.test` with password `synthetic-proof-password`. `seed.py` creates
another disposable proof database when run from `apps/api` with `PYTHONPATH=.`; it records
the database URL in `/private/tmp/s52a-proof-db` and the synthetic patient ID in
`/private/tmp/s52a-proof-info.json`. Start the API with that database URL and
`COOKIE_SECURE=false`; start the web app with `API_BASE_URL=http://127.0.0.1:8100`.
The automatic dispatcher was left unconfigured in the proof server so the queued state
remained visible; the unconfirmed attempt came from the fake provider.
