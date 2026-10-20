"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { recallsHref, type QueueNotice } from "@/features/recalls/links";
import type { RecallQueueView } from "@/lib/api/client";

export function ContactedButton({
  recallId,
  view,
  page,
}: {
  recallId: string;
  view: RecallQueueView;
  page: number;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onClick() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/recalls/${encodeURIComponent(recallId)}/contacted`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.ok) {
        go("contacted");
        return;
      }
      if (response.status === 409) {
        go("changed");
        return;
      }
      if (response.status === 403) {
        setMessage("You do not have access.");
      } else {
        setMessage("Something went wrong.");
      }
    } catch {
      setMessage("Could not reach the server.");
    }
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  function go(notice: QueueNotice) {
    router.push(recallsHref(view, page, notice));
    router.refresh();
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" onClick={onClick} disabled={isSubmitting}>
        Mark contacted
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </span>
  );
}
