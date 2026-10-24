"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { patientLabHref } from "@/features/lab/links";
import { ENTER_A_TITLE, labFailure } from "@/features/lab/notices";
import { createLabWork } from "@/lib/api/client";

export function AddLabForm({ patientId }: { patientId: string }) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    const expectedOn = String(form.get("expected_on") ?? "");
    if (title === "") {
      setMessage(ENTER_A_TITLE);
      return;
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await createLabWork(patientId, title, expectedOn);
      if (!result.ok) {
        setMessage(labFailure(result.error));
        return;
      }
      router.push(patientLabHref(patientId, 1, "added"));
      router.refresh();
    } catch {
      setMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-title">Title</Label>
        <Input id="lab-title" name="title" maxLength={200} aria-invalid={message !== null} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-expected">Expected date</Label>
        <Input id="lab-expected" name="expected_on" type="date" />
      </div>
      <Button type="submit" disabled={isSubmitting}>
        Add lab work
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </form>
  );
}
