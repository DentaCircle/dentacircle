# S5.2b synthetic review evidence

Application commit: `362475f`. All records and messages shown here are synthetic.
No real WhatsApp messages were sent to produce these files. The phone and patient
identifiers are excluded from the cropped screenshots.

- `01-inbox.png` — the inbox flags a conversation that needs reception.
- `02-handoff.png` — reception handling controls and the fixed invitation preview.
- `03-timeline.png` — the synthetic booking appears with the patient WhatsApp actor.
- `04-calendar.png` — the corresponding calendar visit is scheduled.
- `05-follow-up.png` — a follow-up explicitly selected in a separate synthetic run is booked.
- `samples.json` — sanitized fake-provider transcript covering both entry points, an
  existing visit, choices and confirmation, STATUS, STOP, fresh resume and handoff. The
  final portion books an explicitly selected follow-up. Visit identifiers are replaced.

The inbox, conversation, timeline and calendar images use one disposable synthetic database;
the transcript and follow-up image use a second run of the same scripts. They are separate
runs and therefore do not share visit references or dates. The API ran with provider sending
disabled, so queued messages in these images are not evidence of real delivery.

To reproduce, make sure local PostgreSQL is running, then from `apps/api` run:

```sh
PYTHONPATH=src:. .venv/bin/python ../../.shipit/proof/S5.2b/seed.py
PYTHONPATH=src:. .venv/bin/python ../../.shipit/proof/S5.2b/transcript.py
```

The scripts create a new isolated database and write its connection details under the
ignored `.openwa/` folder. Configure the API to use that database with
`MESSAGING_URL=''`, `COOKIE_SECURE=false` and the web rewrite pointed at the API. Sign
in as `proof@example.test` with password `synthetic-proof-password`. Open Messages for
handoff and invitation, the patient timeline for attribution, Calendar for the visit,
and Follow-ups → All open for the booked queue item. Crop any new screenshots to omit
patient IDs, visit references and numbers.

Live OpenWA pairing, actual sending and incoming delivery require the dedicated phones;
the synthetic transcript does not claim those checks passed.
