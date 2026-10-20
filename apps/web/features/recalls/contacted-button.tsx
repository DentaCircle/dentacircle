"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { recallsHref, type QueueNotice } from "@/features/recalls/links";
import { markRecallContacted, type RecallQueueView } from "@/lib/api/client";

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

  function clearSubmissionState() {
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  async function onClick() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await markRecallContacted(recallId);
      if (result.ok) {
        clearSubmissionState();
        go("contacted");
        return;
      }
      if (
        result.error.kind === "api" &&
        result.error.status === 409 &&
        result.error.code === "invalid_status"
      ) {
        clearSubmissionState();
        go("changed");
        return;
      }
      if (result.error.kind === "api" && result.error.code === "patient_inactive") {
        setMessage("This patient is inactive.");
      } else if (result.error.kind === "api" && result.error.status === 403) {
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
