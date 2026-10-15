import { canAdvanceAppointments, canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { buildDays } from "@/features/calendar/build-days";
import { CalendarScreen } from "@/features/calendar/calendar-screen";
import { datesInView, readCalendarQuery } from "@/features/calendar/links";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { getClinicDay, listAppointments, listClinicians, type ApiResult } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type CalendarPageProps = {
  searchParams: Promise<{ view?: string; date?: string; clinician?: string; notice?: string }>;
};

export default async function CalendarPage({ searchParams }: CalendarPageProps) {
  const params = await searchParams;
  const user = await requireUser();
  if (!canBookAppointments(user.roles)) return <CalendarScreen status="forbidden" />;
  const cookie = await sessionCookieHeader();
  const [clinicians, day] = await Promise.all([listClinicians(cookie), getClinicDay(cookie)]);
  if (!clinicians.ok || !day.ok) {
    return <CalendarScreen status={isForbidden(clinicians) || isForbidden(day) ? "forbidden" : "error"} />;
  }
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <CalendarScreen status="error" />;
  }
  const query = readCalendarQuery(
    params,
    today,
    clinicians.data.map((row) => row.id),
  );
  const dates = datesInView(query.view, query.date);
  const first = dates[0];
  const last = dates[dates.length - 1];
  if (first === undefined || last === undefined) return <CalendarScreen status="error" />;
  const listed = await listAppointments(cookie, first, last, query.clinician);
  if (!listed.ok) return <CalendarScreen status={isForbidden(listed) ? "forbidden" : "error"} />;
  const days = buildDays(dates, listed.data, today);
  if (days === null) return <CalendarScreen status="error" />;
  return (
    <CalendarScreen
      status="ready"
      view={query.view}
      date={query.date}
      today={today}
      clinician={query.clinician}
      clinicians={clinicians.data.map((row) => ({ id: row.id, label: row.full_name }))}
      days={days}
      notice={query.notice}
      canAdvance={canAdvanceAppointments(user.roles)}
    />
  );
}

function isForbidden<T>(result: ApiResult<T>): boolean {
  return !result.ok && result.error.kind === "api" && result.error.status === 403;
}
