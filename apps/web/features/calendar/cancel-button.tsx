"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export function CancelButton({
  appointmentId,
  returnHref,
}: {
  appointmentId: string;
  returnHref: string;
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
      const response = await fetch(`/api/appointments/${appointmentId}/cancel`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (response.ok) {
        router.push(withNotice(returnHref, "cancelled"));
        router.refresh();
        return;
      }
      if (response.status === 409) {
        setMessage("This appointment can no longer be cancelled.");
        router.refresh();
      } else if (response.status === 403) {
        setMessage("You do not have access.");
      } else {
        setMessage("Something went wrong.");
      }
    } catch {
      setMessage("Something went wrong.");
    }
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  if (!isConfirming) {
    return (
      <Button type="button" variant="outline" onClick={() => setIsConfirming(true)}>
        Cancel
      </Button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <p>Cancel this appointment?</p>
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
    </div>
  );
}

function withNotice(href: string, notice: string): string {
  const query = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  params.set("notice", notice);
  return `/calendar?${params.toString()}`;
}
