"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { careHref } from "@/features/care/notices";
import { createFollowUp } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/errors";

const DATE_MESSAGE = "Choose a date from today through the next year.";

export function FollowUpForm({ patientId }: { patientId: string }) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [dueOn, setDueOn] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    const result = await createFollowUp(patientId, dueOn);
    if (result.ok) {
      router.push(careHref(patientId));
      router.refresh();
      return;
    }
    if (result.error.kind === "api" && result.error.status === 409 && result.error.code === "follow_up_open") {
      router.push(careHref(patientId, "follow_up_open"));
      router.refresh();
      return;
    }
    setMessage(failureMessage(result.error));
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2">
      <Label htmlFor={`follow-up-date-${patientId}`}>Follow-up date</Label>
      <Input
        id={`follow-up-date-${patientId}`}
        type="date"
        value={dueOn}
        onChange={(event) => setDueOn(event.target.value)}
        aria-invalid={message !== null}
      />
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        Create follow-up
      </Button>
    </form>
  );
}

function failureMessage(error: ApiError): string {
  if (error.kind !== "api") return "Something went wrong.";
  if (error.status === 409 && error.code === "patient_inactive") return "This patient is inactive.";
  if (error.status === 422 && (error.message.includes("before_today") || error.message.includes("beyond_horizon"))) {
    return DATE_MESSAGE;
  }
  if (error.status === 422) return "Check this field.";
  return "Something went wrong.";
}
