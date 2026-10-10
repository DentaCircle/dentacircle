import { requireUser } from "@/features/auth/current-user";
import { canRegisterPatients } from "@/features/patients/access";
import { createdDisplayId, pageFromQuery } from "@/features/patients/links";
import { PatientList, type PatientListProps } from "@/features/patients/patient-list";
import { sessionCookieHeader } from "@/features/patients/session";
import { listPatients } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type PatientsPageProps = {
  searchParams: Promise<{ q?: string; page?: string; created?: string }>;
};

export default async function PatientsPage({ searchParams }: PatientsPageProps) {
  const params = await searchParams;
  const user = await requireUser();
  const query = params.q ?? "";
  const page = pageFromQuery(params.page);
  const result = await listPatients(await sessionCookieHeader(), page, query);
  return (
    <PatientList
      {...viewProps(
        result,
        query,
        page,
        canRegisterPatients(user.roles),
        createdDisplayId(params.created),
      )}
    />
  );
}

function viewProps(
  result: Awaited<ReturnType<typeof listPatients>>,
  query: string,
  page: number,
  canCreate: boolean,
  savedId: string | null,
): PatientListProps {
  const shared = { query, page, pageSize: 20, canCreate, createdDisplayId: savedId, items: [], total: 0 };
  if (!result.ok) {
    const forbidden = result.error.kind === "api" && result.error.status === 403;
    return { ...shared, status: forbidden ? "forbidden" : "error", canCreate: forbidden ? false : canCreate };
  }
  const items = result.data.items.map((patient) => ({
    displayId: patient.display_id,
    fullName: patient.full_name,
    phone: patient.phone,
    dateOfBirth: patient.date_of_birth,
  }));
  if (result.data.total === 0 && query.trim() === "") {
    return { ...shared, status: "empty" };
  }
  if (result.data.total === 0) {
    return { ...shared, status: "no-match" };
  }
  return {
    ...shared,
    status: "ready",
    items,
    total: result.data.total,
    page: result.data.page,
    pageSize: result.data.page_size,
  };
}
