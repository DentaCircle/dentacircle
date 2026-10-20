"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { followUpsHref, type QueueNotice } from "@/features/follow-ups/links";
import { cancelFollowUp, type FollowUpQueueView } from "@/lib/api/client";

export function CancelButton({
  followUpId,
  view,
  page,
}: {
  followUpId: string;
  view: FollowUpQueueView;
  page: number;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onConfirm() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await cancelFollowUp(followUpId);
      if (result.ok) {
        go("cancelled");
        return;
      }
      if (result.error.kind === "api" && result.error.status === 409) {
        go("changed");
        return;
      }
      if (result.error.kind === "api" && result.error.status === 403) {
        setMessage("You do not have access.");
      } else if (result.error.kind === "network" || result.error.kind === "timeout") {
        setMessage("Could not reach the server.");
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
    router.push(followUpsHref(view, page, notice));
    router.refresh();
  }

  if (!isConfirming) {
    return (
      <Button type="button" variant="outline" onClick={() => setIsConfirming(true)}>
        Cancel follow-up
      </Button>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <p>Cancel this follow-up? This cannot be undone.</p>
      <Button type="button" onClick={onConfirm} disabled={isSubmitting}>
        Yes, cancel
      </Button>
      <Button type="button" variant="outline" onClick={() => setIsConfirming(false)}>
        Keep
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </span>
  );
}
