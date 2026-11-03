"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { PatientWorkspace } from "@/features/patients/patient-workspace";
import type { components } from "@/lib/api/schema";

type Patient = components["schemas"]["PatientResponse"];
type Contact = components["schemas"]["ContactBody"];
type History = components["schemas"]["HistoryPage"];
type Connection = components["schemas"]["ConnectionBody"];
type Message = components["schemas"]["MessageBody"];

const TIMEOUT_MS = 10_000;

export function Conversation({ patientId, timezone }: { patientId: string; timezone: string }) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [contact, setContact] = useState<Contact | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [number, setNumber] = useState("");
  const [body, setBody] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const attempt = useRef<{ id: string; body: string } | null>(null);
  const inFlight = useRef(false);
  const loadSequence = useRef(0);
  const root = `/api/patients/${encodeURIComponent(patientId)}`;

  const load = useCallback(async (targetPage = page) => {
    const sequence = ++loadSequence.current;
    setError("");
    try {
      const options = () => ({ cache: "no-store" as const, signal: AbortSignal.timeout(TIMEOUT_MS) });
      const responses = await Promise.all([
        fetch(root, options()),
        fetch(`${root}/messaging-contact`, options()),
        fetch(`${root}/messages?page=${targetPage}`, options()),
        fetch("/api/messaging/connection", options()),
      ]);
      if (responses.some((response) => !response.ok)) {
        if (sequence === loadSequence.current) {
          setError(responses.some((response) => response.status === 403)
            ? "You do not have access to messages."
            : "Conversation could not be loaded.");
        }
        return false;
      }
      const [patientResponse, contactResponse, historyResponse, connectionResponse] = responses;
      const [nextPatient, nextContact, nextHistory, nextConnection] = await Promise.all([
        patientResponse.json() as Promise<Patient>,
        contactResponse.json() as Promise<Contact | null>,
        historyResponse.json() as Promise<History>,
        connectionResponse.json() as Promise<Connection>,
      ]);
      if (sequence !== loadSequence.current) return false;
      setPatient(nextPatient);
      setContact(nextContact);
      setHistory(nextHistory);
      setConnection(nextConnection);
      return true;
    } catch {
      if (sequence === loadSequence.current) setError("Conversation could not be loaded.");
      return false;
    }
  }, [root, page]);

  useEffect(() => { void load(); }, [load]);

  async function link(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${root}/messaging-contact`, {
        method: "PUT",
        signal: AbortSignal.timeout(TIMEOUT_MS),
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ number }),
      });
      if (!response.ok) {
        setError("Number could not be linked. Check the number and test-phone allowlist.");
      } else {
        setContact(await response.json() as Contact);
        setNumber("");
      }
    } catch {
      setError("Number could not be linked.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function markUncertain() {
    setError("Send outcome is uncertain. Refresh and inspect the conversation; sending again reuses this request.");
    setUncertain(true);
    setReviewed(false);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const cleaned = body.trim();
    if (!cleaned || Array.from(cleaned).length > 2000) {
      setError("Enter 1 to 2,000 characters.");
      return;
    }
    if (attempt.current === null) attempt.current = { id: crypto.randomUUID(), body: cleaned };
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${root}/messages`, {
        method: "POST",
        signal: AbortSignal.timeout(TIMEOUT_MS),
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: attempt.current.body, request_id: attempt.current.id }),
      });
      if (response.ok) {
        attempt.current = null;
        setBody("");
        setUncertain(false);
        setReviewed(false);
        if (page === 1) await load(1);
        else setPage(1);
      } else if ([409, 422, 503].includes(response.status)) {
        attempt.current = null;
        setUncertain(false);
        setReviewed(false);
        setError("Message was not sent. Check the connection and patient status.");
      } else {
        markUncertain();
      }
    } catch {
      markUncertain();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const canSend = patient?.status === "active" && contact !== null &&
    connection?.status === "connected" && connection.can_send_text;
  if (patient === null) return error ? <p role="alert">{error}</p> : <p>Loading conversation…</p>;

  return (
    <PatientWorkspace patient={patient} current="messages">
      <section className="space-y-4">
        <h1 className="text-2xl font-semibold">Messages</h1>
        <p>WhatsApp test demo · Synthetic records and allowlisted test phones only.</p>
        <p>
          Connection: {connection?.status ?? "loading"}
          {connection && !connection.can_send_text ? " · Sending unavailable" : ""}
        </p>
        {patient.status === "inactive" ? <p>This patient is inactive. History remains available.</p> : null}
        {contact ? <p>Linked number: {contact.number}</p> : patient.status === "active" ? (
          <form onSubmit={link} className="flex flex-wrap gap-2">
            <label>
              International test number{" "}
              <input className="rounded border p-2" value={number} onChange={(event) => setNumber(event.target.value)} placeholder="+ country code and number" />
            </label>
            <button className="rounded border px-3" disabled={busy || connection?.status === "unconfigured"}>Link number</button>
          </form>
        ) : null}
        <button className="rounded border px-3 py-2" disabled={busy} onClick={() => {
          void load().then((ok) => { if (ok && uncertain) setReviewed(true); });
        }}>Refresh</button>
        {error ? <p role="alert">{error}</p> : null}
        {history === null ? <p>Loading conversation…</p> : history.items.length === 0 ? (
          <p>No messages yet.</p>
        ) : (
          <ol className="space-y-3">
            {history.items.map((message) => <MessageRow key={message.id} message={message} timezone={timezone} />)}
          </ol>
        )}
        {history && history.total > history.page_size ? (
          <div className="flex gap-3">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span>Page {page}</span>
            <button disabled={page * history.page_size >= history.total} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        ) : null}
        <form onSubmit={send} className="space-y-2">
          <label className="block">
            Message
            <textarea className="block w-full rounded border p-2" value={body} onChange={(event) => setBody(event.target.value)} disabled={!canSend || busy || uncertain} maxLength={4000} />
          </label>
          <button className="rounded border px-3 py-2" disabled={!canSend || busy || (uncertain && !reviewed) || !body.trim()}>Send</button>
        </form>
      </section>
    </PatientWorkspace>
  );
}

function MessageRow({ message, timezone }: { message: Message; timezone: string }) {
  const actor = message.direction === "inbound" ? "Patient via WhatsApp" : message.created_by?.name ?? "Staff";
  const state = message.state === "sending" ? "Sending outcome unconfirmed" :
    message.state === "accepted" ? "Accepted by provider" : message.state;
  return (
    <li className="rounded border p-3">
      <p className="text-sm text-muted-foreground">
        {actor} · {new Date(message.created_at).toLocaleString("en-IN", { timeZone: timezone })} · {state}
      </p>
      <p className="whitespace-pre-wrap break-words">{message.body}</p>
    </li>
  );
}
