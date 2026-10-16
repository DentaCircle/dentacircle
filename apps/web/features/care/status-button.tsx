"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { careHref, type CareNotice } from "@/features/care/notices";
import { careFailure } from "@/features/care/outcomes";
import { changeCareItemStatus, type CareStatusTarget } from "@/lib/api/client";

const LABELS: Record<CareStatusTarget, string> = {
  started: "Start",
  completed: "Complete",
  cancelled: "Cancel",
};

const CONFIRMS: Partial<Record<CareStatusTarget, string>> = {
  completed: "Mark as completed?",
  cancelled: "Cancel this item?",
};

const NOTICES: Record<CareStatusTarget, CareNotice> = {
  started: "started",
  completed: "completed",
  cancelled: "cancelled",
};

export function StatusButton({
  patientId,
  itemId,
  target,
}: {
  patientId: string;
  itemId: string;
  target: CareStatusTarget;
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
    const result = await changeCareItemStatus(itemId, target);
    if (result.ok) {
      router.push(careHref(patientId, NOTICES[target]));
      router.refresh();
      return;
    }
    const failure = careFailure(result.error, null);
    if (failure.kind === "reload") {
      router.push(careHref(patientId, failure.notice));
      router.refresh();
      return;
    }
    setMessage(failure.message);
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
