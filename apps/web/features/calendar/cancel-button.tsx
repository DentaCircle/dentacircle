"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Dialog } from "radix-ui";

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

  return (
    <Dialog.Root open={isConfirming} onOpenChange={setIsConfirming}>
      <Dialog.Trigger asChild>
        <Button type="button" variant="outline" size="sm">Cancel</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background p-6 shadow-lg">
          <Dialog.Title className="text-lg font-semibold">Cancel this appointment?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            The appointment will be removed from the calendar.
          </Dialog.Description>
          {message === null ? null : (
            <p role="alert" className="mt-4 text-sm text-destructive">{message}</p>
          )}
          <div className="mt-6 flex flex-wrap gap-2">
            <Button type="button" onClick={onConfirm} disabled={isSubmitting}>Yes, cancel</Button>
            <Button type="button" variant="outline" autoFocus onClick={() => setIsConfirming(false)}>Keep</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function withNotice(href: string, notice: string): string {
  const query = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  params.set("notice", notice);
  return `/calendar?${params.toString()}`;
}
