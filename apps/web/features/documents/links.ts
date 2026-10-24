import { wallDate, wallTime } from "@/features/appointments/wall-time";
import { formatDueOn } from "@/features/care/follow-up-line";
import type { DocumentNotice } from "@/features/documents/notices";
import type { DocumentAppointmentLink, DocumentFollowUpLink } from "@/lib/api/client";

export type DocumentContext =
  | { kind: "visit"; id: string }
  | { kind: "follow-up"; id: string };

/** The documents list refuses a larger page. The picker asks for the next page when there are more. */
export const LINK_EXISTING_PAGE_SIZE = 100;

export function isLinkedToContext(
  item: {
    appointment: { id: string } | null;
    follow_up: { id: string } | null;
  },
  context: DocumentContext,
): boolean {
  if (context.kind === "visit") return item.appointment?.id === context.id;
  return item.follow_up?.id === context.id;
}

export function documentsHref(
  patientId: string,
  page = 1,
  notice?: DocumentNotice,
  context?: DocumentContext | null,
): string {
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (context?.kind === "visit") params.set("appointment_id", context.id);
  if (context?.kind === "follow-up") params.set("follow_up_id", context.id);
  if (notice !== undefined) params.set("notice", notice);
  return `/patients/${patientId}/documents?${params.toString()}`;
}

export function viewerHref(patientId: string, documentId: string): string {
  return `/patients/${patientId}/documents/${documentId}`;
}

export function inlineHref(patientId: string, documentId: string): string {
  return `${downloadHref(patientId, documentId)}?disposition=inline`;
}

/** The download goes through the same `/api` rewrite as every browser call. */
export function downloadHref(patientId: string, documentId: string): string {
  return `/api/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}/file`;
}

export function visitLinkText(link: DocumentAppointmentLink): string {
  const date = wallDate(link.starts_at);
  const time = wallTime(link.starts_at);
  const when = date === null || time === null ? "" : `, ${date} ${time}`;
  return `Visit: ${link.type_name}${when}`;
}

export function followUpLinkText(link: DocumentFollowUpLink): string {
  return `Follow-up due ${formatDueOn(link.due_on)}`;
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}
