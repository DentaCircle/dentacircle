"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  documentsHref,
  isLinkedToContext,
  LINK_EXISTING_PAGE_SIZE,
  type DocumentContext,
} from "@/features/documents/links";
import { linkFailure } from "@/features/documents/notices";
import { listDocumentsInBrowser, updateDocumentLinks } from "@/lib/api/client";

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
}: {
  patientId: string;
  context: DocumentContext;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [rows, setRows] = useState<{ id: string; filename: string }[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const isLoadingRef = useRef(false);

  async function load(nextPage: number) {
    if (isLoadingRef.current) return;
    isLoadingRef.current = true;
    setIsLoading(true);
    setMessage(null);
    try {
      const result = await listDocumentsInBrowser(patientId, nextPage, LINK_EXISTING_PAGE_SIZE);
      if (!result.ok) {
        setMessage("Documents could not be loaded.");
        return;
      }
      const visible = result.data.items
        .filter((item) => !isLinkedToContext(item, context))
        .map((item) => ({ id: item.id, filename: item.filename }));
      setRows((current) => (nextPage === 1 ? visible : [...current, ...visible]));
      setPage(result.data.page);
      setHasMore(result.data.page * result.data.page_size < result.data.total);
    } finally {
      isLoadingRef.current = false;
      setIsLoading(false);
    }
  }

  async function onToggle() {
    const next = !isOpen;
    setIsOpen(next);
    if (next && page === 0) await load(1);
  }

  return (
    <div className="flex flex-col gap-2">
      <Button type="button" variant="outline" onClick={() => void onToggle()}>
        Link a document that is already uploaded
      </Button>
      {isOpen ? (
        <LinkExistingList
          patientId={patientId}
          context={context}
          rows={rows}
          hasMore={hasMore}
          isLoading={isLoading}
          hasLoaded={page > 0}
          message={message}
          onLoadMore={() => void load(page + 1)}
        />
      ) : null}
    </div>
  );
}

function LinkExistingList({
  patientId,
  context,
  rows,
  hasMore,
  isLoading,
  hasLoaded,
  message,
  onLoadMore,
}: {
  patientId: string;
  context: DocumentContext;
  rows: { id: string; filename: string }[];
  hasMore: boolean;
  isLoading: boolean;
  hasLoaded: boolean;
  message: string | null;
  onLoadMore: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      {isLoading && rows.length === 0 ? <p>Loading documents.</p> : null}
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      {hasLoaded && rows.length === 0 && !hasMore && !isLoading ? (
        <p>No other documents to link.</p>
      ) : null}
      {rows.length === 0 ? null : (
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
      )}
      {hasMore ? (
        <Button type="button" variant="outline" disabled={isLoading} onClick={onLoadMore}>
          Load more
        </Button>
      ) : null}
    </div>
  );
}
