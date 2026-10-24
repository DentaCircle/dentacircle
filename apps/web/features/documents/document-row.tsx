import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/features/documents/link-button";
import type { DocumentContext } from "@/features/documents/links";
import type { DocumentRowData } from "@/features/documents/rows";

export function DocumentRow({
  row,
  patientId,
  context,
}: {
  row: DocumentRowData;
  patientId: string;
  context: DocumentContext | null;
}) {
  return (
    <li className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={row.viewerHref} className="break-all font-medium">
          {row.filename}
        </Link>
        <Badge variant="outline">{row.type}</Badge>
        <span>{row.size}</span>
      </div>
      <p>
        {row.uploadedBy}, {row.uploadedAt}
      </p>
      {row.links.map((line) => (
        <p key={line}>{line}</p>
      ))}
      <p className="flex flex-wrap items-center gap-3">
        <a href={row.href}>Download</a>
        {context === null ? null : (
          <LinkButton patientId={patientId} documentId={row.id} context={context} action="unlink" />
        )}
      </p>
    </li>
  );
}
