import { Badge } from "@/components/ui/badge";
import type { DocumentRowData } from "@/features/documents/rows";

export function DocumentRow({ row }: { row: DocumentRowData }) {
  return (
    <li className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="break-all font-medium">{row.filename}</span>
        <Badge variant="outline">{row.type}</Badge>
        <span>{row.size}</span>
      </div>
      <p>
        {row.uploadedBy}, {row.uploadedAt}
      </p>
      <p>
        <a href={row.href}>Download</a>
      </p>
    </li>
  );
}
