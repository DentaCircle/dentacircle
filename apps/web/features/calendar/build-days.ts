import { wallTime } from "@/features/appointments/wall-time";

import { dayHeading } from "@/features/calendar/dates";
import type { CalendarDay } from "@/features/calendar/day-section";
import type { CalendarVisit } from "@/lib/api/client";

export function buildDays(dates: readonly string[], visits: readonly CalendarVisit[], today: string): CalendarDay[] | null {
  const byDate = new Map<string, CalendarDay>();
  for (const date of dates) {
    byDate.set(date, { date, heading: dayHeading(date), isToday: date === today, visits: [] });
  }
  for (const visit of visits) {
    const start = wallTime(visit.starts_at);
    const end = wallTime(visit.ends_at);
    const day = dayForVisit(visit.starts_at, dates);
    const bucket = day === null ? undefined : byDate.get(day);
    if (start === null || end === null || bucket === undefined) return null;
    bucket.visits.push({
      id: visit.id,
      timeRange: `${start}–${end}`,
      patientId: visit.patient.id,
      patientName: visit.patient.full_name,
      displayId: visit.patient.display_id,
      typeName: visit.appointment_type.name,
      clinicianName: visit.clinician.full_name,
      status: visit.status,
    });
  }
  return dates.map((date) => {
    const day = byDate.get(date);
    if (day === undefined) return { date, heading: dayHeading(date), isToday: date === today, visits: [] };
    return day;
  });
}

function dayForVisit(startsAt: string, dates: readonly string[]): string | null {
  const day = startsAt.slice(0, 10);
  if (dates.includes(day)) return day;
  const first = dates[0];
  if (first !== undefined && day < first) return first;
  return null;
}
