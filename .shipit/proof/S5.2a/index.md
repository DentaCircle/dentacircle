# S5.2a proof

Application commit: `e66dd5274aaf03f03970ba6bd92c025058137999`. These captures show the
real application with a disposable PostgreSQL database, synthetic staff and patient records,
and a fake provider. No real WhatsApp account, message, or patient data was used.

1. `01-inbox.png` — Signed in as synthetic staff and opened Messages. The latest queued
   automatic reply is labeled in the inbox.
2. `02-conversation.png` — Opened Sample Patient's Messages and captured the message list.
   The queued and unconfirmed automatic replies appear alongside incoming patient messages.
   The image is clipped above the linked synthetic number.
3. `03-timeline.png` — Opened the patient's Timeline. The visit is attributed to “Patient via
   WhatsApp” and registration still shows the staff actor.

`samples.json` contains sanitized responses from `GET /patients/<patient-id>/messages` and
`GET /patients/<patient-id>/timeline`. Account and patient IDs are omitted and the staff ID
is replaced with a placeholder. The captured response came from the same synthetic app.

The proof server used `http://127.0.0.1:3100` and `http://127.0.0.1:8100`. The synthetic
login is `proof@example.test` with password `synthetic-proof-password`. `seed.py` creates
another disposable proof database when run from `apps/api` with `PYTHONPATH=.`; it records
the database URL in `/private/tmp/s52a-proof-db` and the synthetic patient ID in
`/private/tmp/s52a-proof-info.json`. Start the API with that database URL and
`COOKIE_SECURE=false`; start the web app with `API_BASE_URL=http://127.0.0.1:8100`.
The automatic dispatcher was left unconfigured in the proof server so the queued state
remained visible; the unconfirmed attempt came from the fake provider.

To reproduce from this worktree, first ensure the local PostgreSQL service is running. Then:

```sh
cd apps/api
PYTHONPATH=. uv run python ../../.shipit/proof/S5.2a/seed.py
DATABASE_URL="$(cat /private/tmp/s52a-proof-db)" COOKIE_SECURE=false \
  uv run uvicorn dentacircle.main:app --host 127.0.0.1 --port 8100 --no-access-log
```

In a second terminal:

```sh
cd apps/web
API_BASE_URL=http://127.0.0.1:8100 pnpm exec next dev --hostname 127.0.0.1 --port 3100
```

Open `http://127.0.0.1:3100`, sign in with the synthetic login above, and use the steps for
the three images. The seed creates a new disposable database each time; it never uses the
normal application database for its synthetic rows.
