import Link from "next/link";

import { DocumentRow } from "@/features/documents/document-row";
import { LinkExisting } from "@/features/documents/link-button";
import { documentsHref, type DocumentContext } from "@/features/documents/links";
import { DOCUMENT_NOTICES, type DocumentNotice } from "@/features/documents/notices";
import type { DocumentRowData } from "@/features/documents/rows";
import { UploadForm } from "@/features/documents/upload-form";

export type DocumentsScreenProps = {
  status: "ready" | "empty" | "not-found" | "forbidden" | "error";
  patientId: string;
  rows: DocumentRowData[];
  page: number;
  pageSize: number;
  total: number;
  canUpload: boolean;
  isPatientInactive: boolean;
  notice: DocumentNotice | null;
  context?: DocumentContext | null;
  contextHeading?: string | null;
};

export function DocumentsScreen({
  status,
  patientId,
  rows,
  page,
  pageSize,
  total,
  canUpload,
  isPatientInactive,
  notice,
  context = null,
  contextHeading = null,
}: DocumentsScreenProps) {
  const isLoaded = status === "ready" || status === "empty";
  const emptyText =
    context?.kind === "visit"
      ? "No documents for this visit yet."
      : context?.kind === "follow-up"
        ? "No documents for this follow-up yet."
        : context?.kind === "lab"
          ? "No documents for this lab work yet."
          : "No documents for this patient yet.";
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <Link href={`/patients/${patientId}`}>Patient</Link>
      </div>
      {context === null || contextHeading === null ? null : (
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-medium">{contextHeading}</h2>
          <Link href={documentsHref(patientId)}>Show all documents</Link>
        </div>
      )}
      {notice === null ? null : <p role="status">{DOCUMENT_NOTICES[notice]}</p>}
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Documents could not be loaded.</p> : null}
      {isLoaded && isPatientInactive ? (
        <p>This patient is inactive, so new documents cannot be added.</p>
      ) : null}
      {isLoaded && canUpload && !isPatientInactive ? (
        <UploadForm patientId={patientId} context={context} />
      ) : null}
      {isLoaded && context !== null ? (
        <LinkExisting patientId={patientId} context={context} />
      ) : null}
      {status === "empty" ? <p>{emptyText}</p> : null}
      {status === "ready" ? (
        <ul className="flex flex-col gap-4">
          {rows.map((row) => (
            <DocumentRow key={row.id} row={row} patientId={patientId} context={context} />
          ))}
        </ul>
      ) : null}
      {status === "ready" ? (
        <nav aria-label="Pages" className="flex gap-3">
          {page > 1 ? (
            <Link href={documentsHref(patientId, page - 1, undefined, context)}>Previous</Link>
          ) : (
            <span>Previous</span>
          )}
          {page * pageSize < total ? (
            <Link href={documentsHref(patientId, page + 1, undefined, context)}>Next</Link>
          ) : (
            <span>Next</span>
          )}
        </nav>
      ) : null}
    </section>
  );
}
