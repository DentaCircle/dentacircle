import { requireUser } from "@/features/auth/current-user";
import { canUseLab } from "@/features/lab/access";
import { pageFromQuery } from "@/features/lab/links";
import { isLabNotice } from "@/features/lab/notices";
import { PatientLabScreen, type PatientLabScreenProps } from "@/features/lab/patient-screen";
import { labRow } from "@/features/lab/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { getPatient, listPatientLabWork } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type LabPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string; notice?: string }>;
};

export default async function PatientLabPage({ params, searchParams }: LabPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const page = pageFromQuery(query.page);
  const notice = isLabNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canUseLab(user.roles)) {
    return <PatientLabScreen {...blankProps("forbidden", id, page, notice)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [found, patient] = await Promise.all([
    listPatientLabWork(cookieHeader, id, page),
    getPatient(cookieHeader, id),
  ]);
  if (!found.ok) return <PatientLabScreen {...failureProps(found.error, id, page, notice)} />;
  if (!patient.ok) return <PatientLabScreen {...failureProps(patient.error, id, page, notice)} />;
  return (
    <PatientLabScreen
      status={found.data.total === 0 ? "empty" : "ready"}
      patientId={id}
      rows={found.data.items.map((item) => labRow(item))}
      page={found.data.page}
      pageSize={found.data.page_size}
      total={found.data.total}
      isPatientInactive={patient.data.status === "inactive"}
      notice={notice}
    />
  );
}

function failureProps(
  error: { kind: string; status?: number },
  patientId: string,
  page: number,
  notice: PatientLabScreenProps["notice"],
): PatientLabScreenProps {
  if (error.kind === "api" && error.status === 403) {
    return blankProps("forbidden", patientId, page, notice);
  }
  if (error.kind === "api" && error.status === 404) {
    return blankProps("not-found", patientId, page, notice);
  }
  return blankProps("error", patientId, page, notice);
}

function blankProps(
  status: "not-found" | "forbidden" | "error",
  patientId: string,
  page: number,
  notice: PatientLabScreenProps["notice"],
): PatientLabScreenProps {
  return {
    status,
    patientId,
    rows: [],
    page,
    pageSize: 20,
    total: 0,
    isPatientInactive: false,
    notice,
  };
}
