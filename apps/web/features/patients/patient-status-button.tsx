"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

type PatientStatus = "active" | "inactive";

export function statusLabel(status: PatientStatus): string {
  return status === "active" ? "Active" : "Inactive";
}

export function PatientStatusButton({
  patientId,
  status,
}: {
  patientId: string;
  status: PatientStatus;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [current, setCurrent] = useState(status);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const next = current === "active" ? "inactive" : "active";

  async function onClick() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/patients/${patientId}/status`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ status: next }),
      });
      if (response.ok) {
        setCurrent(next);
        router.refresh();
      } else if (response.status === 403) {
        setMessage("You do not have access.");
      } else {
        setMessage("The status could not be saved.");
      }
    } catch {
      setMessage("Could not reach the server.");
    }
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span>{statusLabel(current)}</span>
      <Button type="button" onClick={onClick} disabled={isSubmitting}>
        {current === "active" ? "Mark inactive" : "Mark active"}
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </div>
  );
}
