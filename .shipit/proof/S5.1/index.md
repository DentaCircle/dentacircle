# S5.1 visual proof

Application commit: `2556342`. All records and messages are synthetic. The application ran
against a disposable PostgreSQL database and a loopback-only fake OpenWA HTTP provider; no
WhatsApp account or real phone was used. The conversation and inactive captures are clipped to
exclude the test number. These captures do not establish live WhatsApp compatibility.

- **01-inbox.png — Inbox.** Sign in as the synthetic clinic admin. Link a synthetic patient,
  send through the fake provider, deliver a synthetic callback, and open Messages.
- **02-conversation.png — Two-way conversation.** Open that patient's conversation and refresh
  after the synthetic callback. The clipped view shows the received and provider-accepted rows.
- **03-unlinked.png — Empty conversation.** Register a second synthetic patient and open its
  Messages tab without linking a number.
- **04-disconnected.png — Disconnected.** Stop the fake provider and refresh the unlinked
  conversation. Sending is unavailable.
- **05-inactive.png — Inactive.** Mark the first synthetic patient inactive and open its
  conversation. The status notice is clipped above the number; its retained history is the
  same history shown in 02.

The provider image inspected for the spike was `openwa/wa-automate` digest
`sha256:d31f5a8f59c4890a302294e9834a25f217a973d80339896ef74cf3d35d903cb3`, with bundled
runtime 4.76.0. The AMD64 variant started Chrome and served its unpaired QR page on
loopback (HTTP 200); the ARM64 variant failed to launch Chrome because a library was missing.
The Compose profile now selects AMD64. Its real pairing, live send and reply, saved-contact licence behavior, restart,
and callback replay against a dedicated account were not tested because test phones and an
account were not available. Callback replay and restart-independent persistence are covered by
local database tests, not a live provider.

Sanitised sample (placeholder identifiers; no real numbers):

```json
POST /integrations/messaging/openwa/events
{"sessionId":"demo","event":"onMessage","data":{"id":"synthetic-id","from":"<allowlisted-direct-address>","body":"Synthetic reply","type":"chat","fromMe":false,"isGroupMsg":false}}
HTTP/1.1 204 No Content
```

A synthetic send through the fake provider returned an outbound message in `accepted` state;
this means provider acceptance only, not WhatsApp delivery.
