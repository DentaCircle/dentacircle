"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CalendarNotice } from "@/features/calendar/links";
import { changeAppointmentStatus } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/errors";

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
  const [followUpDueOn, setFollowUpDueOn] = useState("");
  const confirm = CONFIRMS[target] ?? null;

  async function onConfirm() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    const dueOn = target === "completed" && followUpDueOn !== "" ? followUpDueOn : undefined;
    const result = await changeAppointmentStatus(appointmentId, target, dueOn);
    if (result.ok) {
      router.push(withNotice(returnHref, NOTICES[target]));
      router.refresh();
      return;
    }
    if (result.error.kind === "api" && result.error.status === 409) {
      router.push(withNotice(returnHref, "changed"));
      router.refresh();
      return;
    }
    setMessage(failureMessage(result.error));
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  if (confirm !== null && !isConfirming) {
    return (
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setMessage(null);
          setIsConfirming(true);
        }}
      >
        {LABELS[target]}
      </Button>
    );
  }

  if (confirm !== null) {
    return (
      <div className="flex flex-col gap-2">
        <p>{confirm}</p>
        {target === "completed" ? (
          <div className="flex flex-col gap-1">
            <Label htmlFor={`follow-up-${appointmentId}`}>Follow-up date</Label>
            <Input
              id={`follow-up-${appointmentId}`}
              type="date"
              value={followUpDueOn}
              onChange={(event) => setFollowUpDueOn(event.target.value)}
            />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={onConfirm} disabled={isSubmitting}>
            Yes
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setMessage(null);
              setIsConfirming(false);
            }}
          >
            Keep
          </Button>
          {message === null ? null : (
            <p role="alert" className="text-sm text-destructive">
              {message}
            </p>
          )}
        </div>
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

function failureMessage(error: ApiError): string {
  if (error.kind !== "api") return "Something went wrong.";
  if (error.status === 403) return "You do not have access.";
  if (error.status === 422 && error.message.includes("not_today")) {
    return "Arrived can only be set on the day of the visit.";
  }
  if (error.status === 422 && error.message.includes("not_started")) {
    return "No-show can only be set after the start time.";
  }
  if (
    error.status === 422 &&
    (error.message.includes("before_today") || error.message.includes("beyond_horizon"))
  ) {
    return "Choose a date from today through the next year.";
  }
  return "Something went wrong.";
}

function withNotice(href: string, notice: string): string {
  const query = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  params.set("notice", notice);
  return `/calendar?${params.toString()}`;
}
