import { canBookAppointments } from "@/features/appointments/access";
import { BookPage } from "@/features/appointments/book-page";
import { clinicToday } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { getClinicDay, getPatient, listAppointmentTypes, listClinicians } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type BookAppointmentPageProps = {
  params: Promise<{ id: string }>;
};

export default async function BookAppointmentPage({ params }: BookAppointmentPageProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canBookAppointments(user.roles)) return <BookPage status="forbidden" />;
  const cookie = await sessionCookieHeader();
  const patient = await getPatient(cookie, id);
  if (!patient.ok) {
    if (patient.error.kind === "api" && patient.error.status === 404) return <BookPage status="not-found" />;
    if (patient.error.kind === "api" && patient.error.status === 403) return <BookPage status="forbidden" />;
    return <BookPage status="error" />;
  }
  if (patient.data.status === "inactive") return <BookPage status="inactive" />;
  const [clinicians, types, day] = await Promise.all([
    listClinicians(cookie),
    listAppointmentTypes(cookie),
    getClinicDay(cookie),
  ]);
  if (!clinicians.ok || !types.ok || !day.ok) return <BookPage status="error" />;
  if (clinicians.data.length === 0) return <BookPage status="no-clinicians" />;
  if (types.data.length === 0) return <BookPage status="no-types" />;
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <BookPage status="error" />;
  }
  return (
    <BookPage
      status="ready"
      patientId={patient.data.id}
      today={today}
      clinicians={clinicians.data.map((row) => ({ id: row.id, label: row.full_name }))}
      types={types.data.map((row) => ({ id: row.id, label: row.name }))}
    />
  );
}
