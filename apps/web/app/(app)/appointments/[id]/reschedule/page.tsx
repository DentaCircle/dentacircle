import { canBookAppointments } from "@/features/appointments/access";
import { clinicianChoices } from "@/features/appointments/clinician-choices";
import { ReschedulePage } from "@/features/appointments/reschedule-page";
import { clinicToday, wallDate, wallTime } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { getAppointment, getClinicDay, listClinicians } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type RescheduleRouteProps = {
  params: Promise<{ id: string }>;
};

export default async function RescheduleRoute({ params }: RescheduleRouteProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canBookAppointments(user.roles)) return <ReschedulePage status="forbidden" />;
  const cookie = await sessionCookieHeader();
  const appointment = await getAppointment(cookie, id);
  if (!appointment.ok) {
    if (appointment.error.kind === "api" && appointment.error.status === 404) {
      return <ReschedulePage status="not-found" />;
    }
    if (appointment.error.kind === "api" && appointment.error.status === 403) {
      return <ReschedulePage status="forbidden" />;
    }
    return <ReschedulePage status="error" />;
  }
  if (appointment.data.status !== "scheduled") return <ReschedulePage status="not-scheduled" />;
  const [clinicians, day] = await Promise.all([listClinicians(cookie), getClinicDay(cookie)]);
  if (!clinicians.ok || !day.ok) {
    const forbidden =
      (!clinicians.ok && clinicians.error.kind === "api" && clinicians.error.status === 403) ||
      (!day.ok && day.error.kind === "api" && day.error.status === 403);
    return <ReschedulePage status={forbidden ? "forbidden" : "error"} />;
  }
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <ReschedulePage status="error" />;
  }
  const visitDay = wallDate(appointment.data.starts_at);
  const start = wallTime(appointment.data.starts_at);
  const end = wallTime(appointment.data.ends_at);
  if (visitDay === null || start === null || end === null) return <ReschedulePage status="error" />;
  const assigned = {
    id: appointment.data.clinician.id,
    label: appointment.data.clinician.full_name,
  };
  return (
    <ReschedulePage
      status="ready"
      appointmentId={appointment.data.id}
      patientName={appointment.data.patient.full_name}
      typeName={appointment.data.appointment_type.name}
      currentWhen={`${start}–${end}`}
      clinicians={clinicianChoices(
        assigned,
        clinicians.data.map((row) => ({ id: row.id, label: row.full_name })),
      )}
      initialClinicianId={assigned.id}
      initialDate={visitDay < today ? today : visitDay}
      today={today}
    />
  );
}
