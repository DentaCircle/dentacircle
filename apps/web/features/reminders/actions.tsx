"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function ReminderActions({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(action: "complete" | "cancel") {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/reminders/${id}/${action}`, { method: "POST" });
      if (response.ok) router.refresh();
      else if (response.status === 409) setError("This reminder or visit has changed. Refresh to see the latest state.");
      else if (response.status === 403) setError("You do not have access.");
      else setError("The reminder could not be updated.");
    } catch { setError("The reminder could not be updated."); }
    finally { setBusy(false); }
  }
  return <div className="flex flex-wrap gap-2"><Button size="sm" disabled={busy} onClick={() => act("complete")}>Complete</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => act("cancel")}>Cancel</Button>{error ? <p role="alert">{error}</p> : null}</div>;
}
