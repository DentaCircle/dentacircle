"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { clinicLabHref, patientLabHref } from "@/features/lab/links";
import { labFailure, type LabNotice } from "@/features/lab/notices";
import { changeLabWorkStatus, type LabWorkListView, type LabWorkStatus } from "@/lib/api/client";

type ReturnTarget =
  | { kind: "patient"; patientId: string; page: number }
  | { kind: "clinic"; view: LabWorkListView; page: number };

export function LabStatusActions({
  labWorkId,
  status,
  returnTo,
}: {
  labWorkId: string;
  status: LabWorkStatus;
  returnTo: ReturnTarget;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (status === "collected" || status === "cancelled") return null;

  async function move(next: "ready" | "collected" | "cancelled", notice: LabNotice) {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await changeLabWorkStatus(labWorkId, next);
      if (result.ok) {
        go(notice);
        return;
      }
      if (result.error.kind === "api" && result.error.code === "invalid_status") {
        go("changed");
        return;
      }
      setMessage(labFailure(result.error));
    } catch {
      setMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
      setIsConfirming(false);
    }
  }

  function go(notice: LabNotice) {
    const href =
      returnTo.kind === "patient"
        ? patientLabHref(returnTo.patientId, returnTo.page, notice)
        : clinicLabHref(returnTo.view, returnTo.page, notice);
    router.push(href);
    router.refresh();
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {status === "pending" ? (
        <Button type="button" disabled={isSubmitting} onClick={() => void move("ready", "ready")}>
          Mark ready
        </Button>
      ) : null}
      {status === "ready" ? (
        <Button
          type="button"
          disabled={isSubmitting}
          onClick={() => void move("collected", "collected")}
        >
          Mark collected
        </Button>
      ) : null}
      {isConfirming ? (
        <>
          <p>Cancel this lab work? This cannot be undone.</p>
          <Button
            type="button"
            disabled={isSubmitting}
            onClick={() => void move("cancelled", "cancelled")}
          >
            Yes, cancel
          </Button>
          <Button type="button" variant="outline" onClick={() => setIsConfirming(false)}>
            Keep
          </Button>
        </>
      ) : (
        <Button type="button" variant="outline" onClick={() => setIsConfirming(true)}>
          Cancel
        </Button>
      )}
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </span>
  );
}
