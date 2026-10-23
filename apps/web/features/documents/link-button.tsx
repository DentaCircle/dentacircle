"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { documentsHref, type DocumentContext } from "@/features/documents/links";
import { linkFailure } from "@/features/documents/notices";
import { updateDocumentLinks } from "@/lib/api/client";

export function LinkButton({
  patientId,
  documentId,
  context,
  action,
}: {
  patientId: string;
  documentId: string;
  context: DocumentContext;
  action: "link" | "unlink";
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const field = context.kind === "visit" ? "appointment_id" : "follow_up_id";

  async function onClick() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await updateDocumentLinks(patientId, documentId, {
        [field]: action === "link" ? context.id : null,
      });
      if (!result.ok) {
        setMessage(linkFailure(result.error));
        return;
      }
      router.push(documentsHref(patientId, 1, action === "link" ? "linked" : "unlinked", context));
      router.refresh();
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <span className="flex flex-col gap-1">
      <Button type="button" variant="outline" disabled={isSubmitting} onClick={onClick}>
        {action === "link" ? "Link" : "Unlink"}
      </Button>
      {message === null ? null : (
        <span role="alert" className="text-sm text-destructive">
          {message}
        </span>
      )}
    </span>
  );
}

export function LinkExisting({
  patientId,
  context,
  rows,
}: {
  patientId: string;
  context: DocumentContext;
  rows: { id: string; filename: string }[];
}) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <Button type="button" variant="outline" onClick={() => setIsOpen((open) => !open)}>
        Link a document that is already uploaded
      </Button>
      {isOpen ? (
        rows.length === 0 ? (
          <p>No other documents to link.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {rows.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="break-all">{row.filename}</span>
                <LinkButton
                  patientId={patientId}
                  documentId={row.id}
                  context={context}
                  action="link"
                />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
