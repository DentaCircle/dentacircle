import { canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { canUseRecallQueue } from "@/features/recalls/access";
import { RecallBookPage } from "@/features/recalls/book-page";
import {
  getClinicDay,
  getRecall,
  listAppointmentTypes,
  listClinicians,
} from "@/lib/api/client";

export const dynamic = "force-dynamic";

type RecallBookRouteProps = {
  params: Promise<{ id: string }>;
};

export default async function RecallBookRoute({ params }: RecallBookRouteProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canUseRecallQueue(user.roles) || !canBookAppointments(user.roles)) {
    return <RecallBookPage status="forbidden" />;
  }
  const cookie = await sessionCookieHeader();
  const found = await getRecall(cookie, id);
  if (!found.ok) {
    if (found.error.kind === "api" && found.error.status === 403) {
      return <RecallBookPage status="forbidden" />;
    }
    if (found.error.kind === "api" && found.error.status === 404) {
      return <RecallBookPage status="closed" />;
    }
    return <RecallBookPage status="error" />;
  }
  if (found.data.status === "booked") {
    return <RecallBookPage status="closed" />;
  }
  const [clinicians, types, day] = await Promise.all([
    listClinicians(cookie),
    listAppointmentTypes(cookie),
    getClinicDay(cookie),
  ]);
  if (!clinicians.ok || !types.ok || !day.ok) return <RecallBookPage status="error" />;
  if (clinicians.data.length === 0) return <RecallBookPage status="no-clinicians" />;
  if (types.data.length === 0) return <RecallBookPage status="no-types" />;
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <RecallBookPage status="error" />;
  }
  return (
    <RecallBookPage
      status="ready"
      recallId={found.data.id}
      patient={found.data.patient}
      today={today}
      clinicians={clinicians.data.map((row) => ({ id: row.id, label: row.full_name }))}
      types={types.data.map((row) => ({ id: row.id, label: row.name }))}
    />
  );
}
