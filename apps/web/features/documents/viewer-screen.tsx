import Link from "next/link";

import { documentsHref, inlineHref } from "@/features/documents/links";
import type { DocumentRowData } from "@/features/documents/rows";

export type ViewerScreenProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  patientId: string;
  row: DocumentRowData | null;
};

export function ViewerScreen({ status, patientId, row }: ViewerScreenProps) {
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Document</h1>
        <Link href={documentsHref(patientId)}>Documents</Link>
      </div>
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Documents could not be loaded.</p> : null}
      {status === "ready" && row !== null ? <ViewerBody patientId={patientId} row={row} /> : null}
    </section>
  );
}

function ViewerBody({ patientId, row }: { patientId: string; row: DocumentRowData }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <h2 className="break-all text-lg font-medium">{row.filename}</h2>
      <p>
        {row.type}, {row.size}
      </p>
      <p>
        {row.uploadedBy}, {row.uploadedAt}
      </p>
      {row.links.map((line) => (
        <p key={line}>{line}</p>
      ))}
      <p>
        <a href={row.href}>Download</a>
      </p>
      {row.contentType === "application/pdf" ? (
        <p>
          <a href={inlineHref(patientId, row.id)} target="_blank" rel="noopener noreferrer">
            Open in new tab
          </a>
        </p>
      ) : (
        // The file response is sandboxed. The image cannot run script.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={inlineHref(patientId, row.id)} alt={row.filename} className="max-w-full" />
      )}
    </div>
  );
}
