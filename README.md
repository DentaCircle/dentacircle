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

That example is Monday to Friday, 09:00 to 18:00, with Saturday and Sunday closed. Add a type with `POST /appointment-types`. A second type with the same name in any case returns 409. Deactivate a type with `PUT /appointment-types/{id}` and `"is_active": false`. Types are not deleted.

```sh
curl -b /tmp/dc-cookies -X POST -H 'Content-Type: application/json' \
  -d '{"name":"Polish","duration_minutes":45}' \
  http://127.0.0.1:8000/appointment-types
```

