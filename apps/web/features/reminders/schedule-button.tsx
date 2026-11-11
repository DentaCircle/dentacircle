"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

// Find instants matching the clinic wall time. Ambiguous or missing times are refused.
export function clinicInstant(wall: string, zone: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(wall);
  if (!match) return null;
  const naive = Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5]);
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const found: number[] = [];
  for (let offset = -14 * 60; offset <= 14 * 60; offset++) {
    const instant = naive + offset * 60_000;
    const parts = formatter.formatToParts(instant);
    const value = (name: string) => parts.find((part) => part.type === name)?.value;
    if (`${value("year")}-${value("month")}-${value("day")}T${value("hour")}:${value("minute")}` === wall) found.push(instant);
  }
  return found.length === 1 ? new Date(found[0]).toISOString() : null;
}

export function ScheduleButton({ appointmentId, timezone }: { appointmentId: string; timezone: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const instant = when ? clinicInstant(when, timezone) : null;
    if (when && !instant) { setMessage("Choose a valid, unambiguous clinic time."); return; }
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`/api/appointments/${appointmentId}/reminders`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(instant ? { due_at: instant } : {}) });
      if (response.ok) { setMessage("Reminder scheduled."); setOpen(false); router.refresh(); }
      else if (response.status === 409) setMessage("This visit changed or already has a pending reminder.");
      else if (response.status === 422) setMessage("Choose a time from now until before the visit.");
      else if (response.status === 403) setMessage("You do not have access.");
      else setMessage("Reminder could not be scheduled.");
    } catch { setMessage("Reminder could not be scheduled."); }
    finally { setBusy(false); }
  }
  return <div>
    <Button type="button" variant="outline" size="sm" onClick={() => setOpen(!open)}>Schedule reminder</Button>
    {open ? <form onSubmit={submit} className="mt-2 flex flex-col gap-2"><label>Due time ({timezone}; leave blank for now)<input className="block border p-1" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></label><Button type="submit" disabled={busy}>Schedule</Button></form> : null}
    {message ? <p role="status">{message}</p> : null}
  </div>;
}
