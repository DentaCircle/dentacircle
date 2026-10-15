"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import type { CalendarNotice } from "@/features/calendar/links";

export type StatusTarget = "arrived" | "in_progress" | "completed" | "no_show";

const LABELS: Record<StatusTarget, string> = {
  arrived: "Arrived",
  in_progress: "Start",
  completed: "Complete",
  no_show: "No-show",
};

const CONFIRMS: Partial<Record<StatusTarget, string>> = {
  completed: "Mark as completed?",
  no_show: "Mark as no-show?",
};

const NOTICES: Record<StatusTarget, CalendarNotice> = {
  arrived: "arrived",
  in_progress: "in_progress",
  completed: "completed",
  no_show: "no_show",
};

export function StatusButton({
  appointmentId,
  returnHref,
  target,
}: {
  appointmentId: string;
  returnHref: string;
  target: StatusTarget;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const confirm = CONFIRMS[target] ?? null;

  async function onConfirm() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/appointments/${appointmentId}/status`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ status: target }),
      });
      if (response.ok) {
        router.push(withNotice(returnHref, NOTICES[target]));
        router.refresh();
        return;
      }
      if (response.status === 409) router.refresh();
      setMessage(await failureMessage(response));
    } catch {
      setMessage("Something went wrong.");
    }
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  if (confirm !== null && !isConfirming) {
    return (
      <Button type="button" variant="outline" onClick={() => setIsConfirming(true)}>
        {LABELS[target]}
      </Button>
    );
  }

  if (confirm !== null) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p>{confirm}</p>
        <Button type="button" onClick={onConfirm} disabled={isSubmitting}>
          Yes
        </Button>
        <Button type="button" variant="outline" onClick={() => setIsConfirming(false)}>
          Keep
        </Button>
        {message === null ? null : (
          <p role="alert" className="text-sm text-destructive">
            {message}
          </p>
        )}
      </div>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" onClick={onConfirm} disabled={isSubmitting}>
        {LABELS[target]}
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </span>
  );
}

async function failureMessage(response: Response): Promise<string> {
  if (response.status === 409) return "This appointment's status has already changed.";
  if (response.status === 403) return "You do not have access.";
  if (response.status === 422) {
    const detail = await readValidationMessage(response);
    if (detail.includes("not_today")) return "Arrived can only be set on the day of the visit.";
    if (detail.includes("not_started")) return "No-show can only be set after the start time.";
  }
  return "Something went wrong.";
}

async function readValidationMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || !("error" in body)) return "";
    const error = body.error;
    if (typeof error !== "object" || error === null || !("message" in error)) return "";
    return typeof error.message === "string" ? error.message : "";
  } catch {
    return "";
  }
}

function withNotice(href: string, notice: string): string {
  const query = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  params.set("notice", notice);
  return `/calendar?${params.toString()}`;
}
