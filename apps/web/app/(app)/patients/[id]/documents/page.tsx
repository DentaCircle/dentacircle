import { requireUser } from "@/features/auth/current-user";
import { canUseDocuments } from "@/features/documents/access";
import { DocumentsScreen, type DocumentsScreenProps } from "@/features/documents/documents-screen";
import { pageFromQuery } from "@/features/documents/links";
import { isDocumentNotice } from "@/features/documents/notices";
import { documentRow } from "@/features/documents/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { getPatient, listDocuments } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type DocumentsPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string; notice?: string }>;
};

export default async function DocumentsPage({ params, searchParams }: DocumentsPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const page = pageFromQuery(query.page);
  const notice = isDocumentNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canUseDocuments(user.roles)) {
    return <DocumentsScreen {...blankProps("forbidden", id, page)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [documents, patient] = await Promise.all([
    listDocuments(cookieHeader, id, page),
    getPatient(cookieHeader, id),
  ]);
  if (!documents.ok) return <DocumentsScreen {...failureProps(documents.error, id, page)} />;
  if (!patient.ok) return <DocumentsScreen {...failureProps(patient.error, id, page)} />;
  return (
    <DocumentsScreen
      status={documents.data.total === 0 ? "empty" : "ready"}
      patientId={id}
      rows={documents.data.items.map((item) => documentRow(id, item))}
      page={documents.data.page}
      pageSize={documents.data.page_size}
      total={documents.data.total}
      canUpload
      isPatientInactive={patient.data.status === "inactive"}
      notice={notice}
    />
  );
}

function failureProps(
  error: { kind: string; status?: number },
  patientId: string,
  page: number,
): DocumentsScreenProps {
  if (error.kind === "api" && error.status === 403) return blankProps("forbidden", patientId, page);
  if (error.kind === "api" && error.status === 404) return blankProps("not-found", patientId, page);
  return blankProps("error", patientId, page);
}

function blankProps(
  status: "not-found" | "forbidden" | "error",
  patientId: string,
  page: number,
): DocumentsScreenProps {
  return {
    status,
    patientId,
    rows: [],
    page,
    pageSize: 20,
    total: 0,
    canUpload: false,
    isPatientInactive: false,
    notice: null,
  };
}
