import { addCalendarDays } from "@/features/appointments/wall-time";

import { isIsoDate, mondayOfWeek } from "@/features/calendar/dates";

export type CalendarViewMode = "day" | "week";

export type CalendarNotice =
  | "cancelled"
  | "rescheduled"
  | "arrived"
  | "in_progress"
  | "completed"
  | "no_show";

export const CALENDAR_NOTICES: Record<CalendarNotice, string> = {
  cancelled: "Appointment cancelled.",
  rescheduled: "Appointment rescheduled.",
  arrived: "Marked arrived.",
  in_progress: "Marked in progress.",
  completed: "Marked completed.",
  no_show: "Marked no-show.",
};

const CALENDAR_NOTICE_NAMES: readonly CalendarNotice[] = [
  "cancelled",
  "rescheduled",
  "arrived",
  "in_progress",
  "completed",
  "no_show",
];

export function isCalendarNotice(value: string | undefined): value is CalendarNotice {
  return CALENDAR_NOTICE_NAMES.some((notice) => notice === value);
}

export type CalendarQuery = {
  view: CalendarViewMode;
  date: string;
  clinician: string | null;
  notice: CalendarNotice | null;
};

export function readCalendarQuery(
  params: { view?: string; date?: string; clinician?: string; notice?: string },
  today: string,
  clinicianIds: readonly string[],
): CalendarQuery {
  const view: CalendarViewMode = params.view === "week" ? "week" : "day";
  const date = params.date !== undefined && isIsoDate(params.date) ? params.date : today;
  const clinician =
    params.clinician !== undefined && clinicianIds.includes(params.clinician) ? params.clinician : null;
  const notice = isCalendarNotice(params.notice) ? params.notice : null;
  return { view, date, clinician, notice };
}

export function calendarHref(query: {
  view: CalendarViewMode;
  date: string;
  clinician: string | null;
  notice?: CalendarNotice | null;
}): string {
  const params = new URLSearchParams();
  params.set("view", query.view);
  params.set("date", query.date);
  if (query.clinician !== null && query.clinician !== "") params.set("clinician", query.clinician);
  if (query.notice !== undefined && query.notice !== null) params.set("notice", query.notice);
  return `/calendar?${params.toString()}`;
}

export function stepDate(date: string, view: CalendarViewMode, direction: -1 | 1): string {
  const days = view === "week" ? 7 : 1;
  return addCalendarDays(date, direction * days);
}

export function datesInView(view: CalendarViewMode, date: string): string[] {
  if (view === "day") return [date];
  const monday = mondayOfWeek(date);
  return Array.from({ length: 7 }, (_, index) => addCalendarDays(monday, index));
}
