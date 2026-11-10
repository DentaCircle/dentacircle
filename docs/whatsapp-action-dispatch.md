# WhatsApp action foundation

S5.2a supplies the internal booking actor and reply queue used by the later conversation
slice. It does not start a booking dialogue or send an automatic reply by itself. A
credential-verified callback can pass a linked inbound message to an internal action; the
message, action and queued reply commit together. Booking records that message as the
actor, and the timeline calls it “Patient via WhatsApp”.

The API starts an in-process dispatcher when the messaging URL, API key, callback secret,
clinic, account and allowlist are configured. It checks the current contact, account,
allowlist and patient before claiming a queued reply. Replies for each contact are claimed
in order. A bounded provider call holds a local process fence, including when the dispatcher
process dies while its sending child is still alive. After the fence is free, an abandoned
claim becomes `unknown`; it is never sent again. Queued replies can resume on restart.
Provider acceptance does not prove delivery. Staff sends share the contact fence and use
bounded provider calls too. If the fence is busy, the staff attempt is recorded as failed;
a replay of the same request id returns that attempt without sending it again. A PostgreSQL
advisory gate serializes patient status changes with staff sends without keeping a patient
row locked during the provider call.

This is a local, single-host demo. All API processes using the same database must run on
the same host and share the same temporary directory and operating-system user so that the
contact fence is shared. Separate containers or hosts with independent temporary directories
are not supported by this fence. Use synthetic records and allowlisted test numbers only.
The live OpenWA pairing and delivery checks remain deferred as recorded in S5.1.

Migration `0022_whatsapp_actions` preserves old staff attribution and outbound history.
Downgrading after WhatsApp-attributed records exist cannot restore the old mandatory staff
actor without losing provenance, so the downgrade fails rather than deleting those records.
