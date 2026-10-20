import { wallDate } from "@/features/appointments/wall-time";
import { calendarHref } from "@/features/calendar/links";
import type { TimelineItem } from "@/lib/api/client";

export function timelineHref(patientId: string, page: number): string {
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `/patients/${patientId}/timeline?${params.toString()}`;
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}

export function entryHref(patientId: string, item: TimelineItem): string | null {
  if (item.kind.startsWith("visit_") && item.subject !== null && "starts_at" in item.subject) {
    const date = wallDate(item.subject.starts_at);
    if (date === null) return null;
    return calendarHref({ view: "day", date, clinician: null });
  }
  if (item.kind.startsWith("care_")) return `/patients/${patientId}/care`;
  return null;
}
