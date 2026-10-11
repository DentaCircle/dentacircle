import { requireUser } from "@/features/auth/current-user";
import { canRegisterPatients } from "@/features/patients/access";
import { PatientDetail, registeredOn, type PatientDetailProps } from "@/features/patients/patient-detail";
import { sessionCookieHeader } from "@/features/patients/session";
import { getPatient } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type PatientDetailPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ saved?: string }>;
};

export default async function PatientDetailPage({ params, searchParams }: PatientDetailPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const user = await requireUser();
  const saved = query.saved === "1";
  if (!canRegisterPatients(user.roles)) {
    return <PatientDetail status="forbidden" patient={null} canEdit={false} saved={false} />;
  }
  const result = await getPatient(await sessionCookieHeader(), id);
  if (!result.ok) {
    return <PatientDetail {...failureProps(result.error)} saved={false} />;
  }
  const patient = result.data;
  return (
    <PatientDetail
      status="ready"
      canEdit
      saved={saved}
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
): Pick<PatientDetailProps, "status" | "patient" | "canEdit"> {
  const forbidden = error.kind === "api" && error.status === 403;
  const missing = error.kind === "api" && error.status === 404;
  if (forbidden) return { status: "forbidden", patient: null, canEdit: false };
  if (missing) return { status: "not-found", patient: null, canEdit: false };
  return { status: "error", patient: null, canEdit: false };
}
