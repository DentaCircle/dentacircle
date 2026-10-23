import { wallDate, wallTime } from "@/features/appointments/wall-time";
import { downloadHref, followUpLinkText, viewerHref, visitLinkText } from "@/features/documents/links";
import { sizeLabel, typeLabel } from "@/features/documents/sizes";
import type { DocumentItem } from "@/lib/api/client";

export type DocumentRowData = {
  id: string;
  filename: string;
  type: string;
  size: string;
  uploadedBy: string;
  uploadedAt: string;
  href: string;
  viewerHref: string;
  links: string[];
  contentType: DocumentItem["content_type"];
};

export function documentRow(patientId: string, item: DocumentItem): DocumentRowData {
  const date = wallDate(item.uploaded_at);
  const time = wallTime(item.uploaded_at);
  const links: string[] = [];
  if (item.appointment !== null) links.push(visitLinkText(item.appointment));
  if (item.follow_up !== null) links.push(followUpLinkText(item.follow_up));
  return {
    id: item.id,
    filename: item.filename,
    type: typeLabel(item.content_type),
    size: sizeLabel(item.size_bytes),
    uploadedBy: item.uploaded_by.name,
    uploadedAt: date === null || time === null ? "—" : `${date} ${time}`,
    href: downloadHref(patientId, item.id),
    viewerHref: viewerHref(patientId, item.id),
    links,
    contentType: item.content_type,
  };
}
