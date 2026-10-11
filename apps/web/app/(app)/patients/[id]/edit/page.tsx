import { requireUser } from "@/features/auth/current-user";
import { canRegisterPatients } from "@/features/patients/access";
import { EditPatientScreen } from "@/features/patients/edit-patient-screen";
import { PatientDetail } from "@/features/patients/patient-detail";
import { sessionCookieHeader } from "@/features/patients/session";
import { getPatient } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type EditPatientPageProps = {
  params: Promise<{ id: string }>;
};

export default async function EditPatientPage({ params }: EditPatientPageProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canRegisterPatients(user.roles)) {
    return <EditPatientScreen canEdit={false} />;
  }
  const result = await getPatient(await sessionCookieHeader(), id);
  if (!result.ok) {
    return (
      <PatientDetail
        status={detailStatus(result.error)}
        patient={null}
        canEdit={false}
        saved={false}
      />
    );
  }
  return (
    <EditPatientScreen
      canEdit
      patientId={result.data.id}
      initial={{
        fullName: result.data.full_name,
        phone: result.data.phone,
        dateOfBirth: result.data.date_of_birth ?? "",
      }}
    />
  );
}

function detailStatus(error: { kind: string; status?: number }): "forbidden" | "not-found" | "error" {
  if (error.kind === "api" && error.status === 403) return "forbidden";
  if (error.kind === "api" && error.status === 404) return "not-found";
  return "error";
}
