"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { documentsHref } from "@/features/documents/links";
import { CHOOSE_A_FILE, problemMessage, uploadFailure } from "@/features/documents/notices";
import { ACCEPT, fileProblem } from "@/features/documents/sizes";
import { uploadDocument } from "@/lib/api/client";

export function UploadForm({ patientId }: { patientId: string }) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    setMessage(null);
    const file = inputRef.current?.files?.[0];
    if (file === undefined) {
      setMessage(CHOOSE_A_FILE);
      return;
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const problem = await fileProblem(file);
      if (problem !== null) {
        setMessage(problemMessage(problem));
        return;
      }
      const result = await uploadDocument(patientId, file);
      if (!result.ok) {
        setMessage(uploadFailure(result.error));
        return;
      }
      formRef.current?.reset();
      router.push(documentsHref(patientId, 1, "uploaded"));
      router.refresh();
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} className="flex flex-col gap-2">
      <Label htmlFor="document-file">File</Label>
      <input
        ref={inputRef}
        id="document-file"
        type="file"
        accept={ACCEPT}
        className="text-sm"
        aria-invalid={message !== null}
      />
      <p className="text-sm text-muted-foreground">PDF, PNG or JPEG, up to 8 MB.</p>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <div>
        <Button type="submit" disabled={isSubmitting}>
          Upload
        </Button>
      </div>
    </form>
  );
}
