"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { messageActor, messageState } from "@/features/messages/message-labels";

import type { components } from "@/lib/api/schema";

type InboxPage = components["schemas"]["InboxPage"];
type Connection = components["schemas"]["ConnectionBody"];

export function Inbox({ timezone }: { timezone: string }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<InboxPage | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const options = () => ({ cache: "no-store" as const, signal: AbortSignal.timeout(10_000) });
      const [response, status] = await Promise.all([
        fetch(`/api/messages?page=${page}`, options()),
        fetch("/api/messaging/connection", options()),
      ]);
      if (!response.ok) {
        setError(response.status === 403
          ? "You do not have access to messages."
          : "Messages could not be loaded.");
        return;
      }
      if (!status.ok) {
        setError("Connection status could not be loaded.");
        return;
      }
      setConnection(await status.json() as Connection);
      setData(await response.json() as InboxPage);
    } catch {
      setError("Messages could not be loaded.");
    }
  }, [page]);

  useEffect(() => { void load(); }, [load]);

  return (
    <section className="space-y-5">
      <h1 className="text-2xl font-semibold">Messages</h1>
      <p>WhatsApp test demo · Synthetic records and allowlisted test phones only.</p>
      <p>
        Connection: {connection?.status ?? "loading"}
        {connection && !connection.can_send_text ? " · Sending unavailable" : ""}
      </p>
      <button className="rounded border px-3 py-2" onClick={() => void load()}>Refresh</button>
      {error ? <p role="alert">{error}</p> : data === null ? <p>Loading messages…</p> :
        data.items.length === 0 ? <p>No conversations yet.</p> : (
          <ul className="space-y-3">
            {data.items.map((row) => (
              <li key={row.patient.id} className="rounded-lg border p-4">
                <Link className="font-semibold underline" href={`/patients/${row.patient.id}/messages`}>
                  {row.patient.full_name} · {row.patient.display_id}
                </Link>
                {row.patient.status === "inactive" ? <span> · Inactive</span> : null}
                <p className="whitespace-pre-wrap break-words">{row.latest_message.body}</p>
                <p className="text-sm text-muted-foreground">
                  {messageActor(row.latest_message)} · {messageState(row.latest_message)} · {row.message_count} messages · {new Date(row.latest_message.created_at).toLocaleString("en-IN", { timeZone: timezone })}
                </p>
              </li>
            ))}
          </ul>
        )}
      {data && data.total > data.page_size ? (
        <div className="flex gap-3">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page}</span>
          <button disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      ) : null}
    </section>
  );
}
