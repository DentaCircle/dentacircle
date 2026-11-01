# Dentacircle

Coordination workflow for an outpatient clinic. See PRODUCT.md for scope.

## Setup

1. Install [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), and Docker.
2. Clone this repo and `cd` into it.
3. Copy `.env.example` to `.env`.
4. Install and check both apps: `make check`.
5. Start the stack: `make dev`. This starts PostgreSQL, waits until it is healthy, applies migrations, then runs the API (port 8000) and the web app (port 3000). Ctrl-C stops both apps. Open `http://localhost:3000`. You are sent to the login page.
6. Create a user in another terminal. The password is prompted, or read from `CREATE_USER_PASSWORD`, never passed as an argument:

   ```sh
   make create-user ARGS='--clinic "Synthetic Clinic" --email a@x.test --name "Synthetic Person" --roles clinician'
   ```

7. Sign in on the login page. The dashboard shows that name, role and clinic.

`make api-dev` and `make web-dev` still start one app each, after `make db-up` and `make migrate`. `curl http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

`API_BASE_URL` is read by the web server when it calls the API and when it proxies `/api`. It defaults to `http://127.0.0.1:8000`. The browser calls `/api` on the web origin. Regenerate the typed client after an API shape change with `make api-types`.

`make check` lints, type checks and tests `apps/api` and `apps/web`. Database tests, including the smoke test, run only when `DATABASE_URL` is set. Export it from `.env` before `make check` if you want those tests to connect:

```sh
set -a && source .env && set +a && make check
```

Stop the database with `make db-down`.

Python 3.12 is pinned in `apps/api/.python-version`. `uv sync` installs it. Node 22 or newer is required for `apps/web`.

`LOG_LEVEL` defaults to `INFO`. Set `LOG_LEVEL=DEBUG` in `.env` on your machine when you need a full traceback. That is for local work with synthetic data.

The M3 click-through, with who signs in and what to click, is in [docs/demo-m3.md](docs/demo-m3.md).

`SESSION_TTL_HOURS` defaults to 12. `COOKIE_SECURE` defaults to true. `.env.example` sets it to false so the session cookie works on `http://localhost`.

## Hours and appointment types

There is no settings screen yet. A `clinic_admin` changes them with the API. Sign in first and keep the cookie. The password is the one you set with `make create-user`, not an argument.

```sh
curl -c /tmp/dc-cookies -H 'Content-Type: application/json' \
  -d '{"email":"admin@x.test","password":"the-password-you-set"}' \
  http://127.0.0.1:8000/auth/login

curl -b /tmp/dc-cookies http://127.0.0.1:8000/clinic/day
curl -b /tmp/dc-cookies http://127.0.0.1:8000/appointment-types
```

`PUT /clinic/day` replaces the timezone, the default duration and the whole hours list. Leave a weekday out to close that day. Send two intervals on one weekday when there is a break. Times are the clinic's local wall time.

```sh
curl -b /tmp/dc-cookies -X PUT -H 'Content-Type: application/json' \
  -d '{"timezone":"Asia/Kolkata","default_appointment_minutes":30,"working_hours":[{"weekday":0,"opens_at":"09:00:00","closes_at":"18:00:00"},{"weekday":1,"opens_at":"09:00:00","closes_at":"18:00:00"},{"weekday":2,"opens_at":"09:00:00","closes_at":"18:00:00"},{"weekday":3,"opens_at":"09:00:00","closes_at":"18:00:00"},{"weekday":4,"opens_at":"09:00:00","closes_at":"18:00:00"}]}' \
  http://127.0.0.1:8000/clinic/day
```

That example is Monday to Friday, 09:00 to 18:00, with Saturday and Sunday closed. Add a type with `POST /appointment-types`. A second type with the same name in any case returns 409. Deactivate a type with `PUT /appointment-types/{id}` and `"is_active": false`. Types are not deleted. `recall_after_months` is optional: leave it out for no recall, or send a whole number from 1 to 60. On `PUT`, leaving it out keeps the current interval, and `null` clears it. New clinics already have Scaling at 6 months.

```sh
curl -b /tmp/dc-cookies -X POST -H 'Content-Type: application/json' \
  -d '{"name":"Polish","duration_minutes":45}' \
  http://127.0.0.1:8000/appointment-types
```


### WhatsApp test inbox (optional)

This is a controlled demo for synthetic records and explicitly allowlisted test phones.
OpenWA is unofficial and WhatsApp still processes messages; do not use real patient data.
The bundled image is pinned to digest `sha256:d31f5a8f59c4890a302294e9834a25f217a973d80339896ef74cf3d35d903cb3`
with bundled `@open-wa/wa-automate` 4.76.0. `--no-update` keeps that runtime fixed. Saved
contacts or existing chats are required for licence-free sends; live compatibility must be
checked with the dedicated test account. No licence purchase is required or configured.

1. Create `.openwa/cli.config.json` locally, keep it private, and replace both secrets and
   the session name below. Use a dedicated account and save the allowlisted test contacts in
   that account. The callback address reaches the API on the Docker host. Never commit the file.

   ```json
   {
     "sessionId": "dentacircle-demo",
     "sessionDataPath": "/sessions",
     "key": "replace-with-a-long-random-api-key",
     "autoEmoji": false,
     "qrLogSkip": true,
     "logging": [{"type": "console", "options": {"silent": true}}],
     "webhook": [{
       "url": "http://host.docker.internal:8000/integrations/messaging/openwa/events",
       "events": ["onMessage"],
       "requestConfig": {"headers": {"X-Webhook-Secret": "replace-with-a-different-random-secret"}}
     }]
   }
   ```

2. Add `MESSAGING_URL=http://127.0.0.1:8080`, `MESSAGING_API_KEY`,
   `MESSAGING_CALLBACK_SECRET`, `MESSAGING_ACCOUNT` (the session ID), `MESSAGING_CLINIC_ID`
   (the clinic UUID), and comma-separated E.164 `MESSAGING_ALLOWLIST` to the local `.env`.
   The secrets must match the private OpenWA configuration. Restart the API after changes.
3. Start the regular app with `make dev`. In a separate terminal run
   `docker compose --profile messaging up -d openwa`, then open `http://127.0.0.1:8080`
   while the provider is waiting for pairing. Scan its QR with the dedicated account. The
   container has logging disabled because this release prints request bodies and its API key;
   do not record or share the QR. Its port is loopback-only.
4. Open Messages, link an active synthetic patient to an allowlisted saved contact, send a
   test message, reply from the test phone and press Refresh. Sending never marks a follow-up
   or recall contacted. Provider acceptance is not a delivery receipt. An uncertain send must
   be inspected, not blindly retried.
5. Stop the bridge with `docker compose --profile messaging stop openwa`. The private named
   session volume remains for a restart. To disconnect the account, log out in WhatsApp's
   linked devices; removing the volume destroys the local session and requires pairing again.

The pinned v4 webhook has an in-memory queue and does not retry failed callbacks or retain a
journal across restarts. A 503 signals a failed database write, but this provider may drop that
message; this demo does not promise durable delivery during outages. Manual callback replay is
safe by provider message ID. No webhook bodies or provider errors are stored in app logs.
