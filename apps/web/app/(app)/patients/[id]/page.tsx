import { canBookAppointments } from "@/features/appointments/access";
import { wallDate, wallTime } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { canRegisterPatients } from "@/features/patients/access";
import {
  PatientDetail,
  registeredOn,
  type PatientDetailProps,
  type UpcomingAppointment,
} from "@/features/patients/patient-detail";
import { sessionCookieHeader } from "@/features/patients/session";
import { getPatient, listUpcomingAppointments } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type PatientDetailPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ saved?: string; booked?: string }>;
};

export default async function PatientDetailPage({ params, searchParams }: PatientDetailPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const user = await requireUser();
  const saved = query.saved === "1";
  const booked = query.booked === "1";
  if (!canRegisterPatients(user.roles)) {
    return (
      <PatientDetail
        status="forbidden"
        patient={null}
        canEdit={false}
        canBook={false}
        saved={false}
        booked={false}
        upcomingItems={null}
      />
    );
  }
  const cookie = await sessionCookieHeader();
  const result = await getPatient(cookie, id);
  if (!result.ok) {
    return <PatientDetail {...failureProps(result.error)} saved={false} booked={false} />;
  }
  const patient = result.data;
  const upcoming = await listUpcomingAppointments(cookie, id);
  return (
    <PatientDetail
      status="ready"
      canEdit
      canBook={canBookAppointments(user.roles)}
      saved={saved}
      booked={booked}
      upcomingItems={upcoming.ok ? upcomingItems(upcoming.data) : null}
      patient={{
        id: patient.id,
        displayId: patient.display_id,
        fullName: patient.full_name,
        phone: patient.phone,
        dateOfBirth: patient.date_of_birth,
        status: patient.status,
        registeredOn: registeredOn(patient.created_at),
      }}
    />
  );
}

function failureProps(
  error: { kind: string; status?: number },
): Pick<PatientDetailProps, "status" | "patient" | "canEdit" | "canBook" | "upcomingItems"> {
  const forbidden = error.kind === "api" && error.status === 403;
  const missing = error.kind === "api" && error.status === 404;
  const base = { patient: null, canEdit: false, canBook: false, upcomingItems: null } as const;
  if (forbidden) return { status: "forbidden", ...base };
  if (missing) return { status: "not-found", ...base };
  return { status: "error", ...base };
}

function upcomingItems(
  rows: {
    id: string;
    starts_at: string;
    appointment_type: { name: string };
    clinician: { full_name: string };
  }[],
): UpcomingAppointment[] {
  const items: UpcomingAppointment[] = [];
  for (const row of rows) {
    const date = wallDate(row.starts_at);
    const time = wallTime(row.starts_at);
    if (date === null || time === null) continue;
    items.push({
      id: row.id,
      date,
      time,
      typeName: row.appointment_type.name,
      clinicianName: row.clinician.full_name,
    });
  }
  return items;
}
