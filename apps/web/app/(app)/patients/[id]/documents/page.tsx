import { wallDate, wallTime } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { formatDueOn } from "@/features/care/follow-up-line";
import { canUseDocuments } from "@/features/documents/access";
import { DocumentsScreen, type DocumentsScreenProps } from "@/features/documents/documents-screen";
import { pageFromQuery, type DocumentContext } from "@/features/documents/links";
import { isDocumentNotice } from "@/features/documents/notices";
import { documentRow } from "@/features/documents/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import {
  getAppointment,
  getPatient,
  listDocuments,
  type DocumentItem,
} from "@/lib/api/client";

export const dynamic = "force-dynamic";

type DocumentsPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    page?: string;
    notice?: string;
    appointment_id?: string;
    follow_up_id?: string;
  }>;
};

export default async function DocumentsPage({ params, searchParams }: DocumentsPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const page = pageFromQuery(query.page);
  const notice = isDocumentNotice(query.notice) ? query.notice : null;
  const context = readContext(query);
  const user = await requireUser();
  if (!canUseDocuments(user.roles)) {
    return <DocumentsScreen {...blankProps("forbidden", id, page)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const filter =
    context?.kind === "visit"
      ? { appointmentId: context.id }
      : context?.kind === "follow-up"
        ? { followUpId: context.id }
        : undefined;
  const [documents, patient, others] = await Promise.all([
    listDocuments(cookieHeader, id, page, 20, filter),
    getPatient(cookieHeader, id),
    context === null
      ? Promise.resolve(null)
      : listDocuments(cookieHeader, id, 1, 100),
  ]);
  if (!documents.ok) return <DocumentsScreen {...failureProps(documents.error, id, page)} />;
  if (!patient.ok) return <DocumentsScreen {...failureProps(patient.error, id, page)} />;
  if (others !== null && !others.ok) {
    return <DocumentsScreen {...failureProps(others.error, id, page)} />;
  }
  const heading = await contextHeading(cookieHeader, id, context, documents.data.items);
  const linkedIds = new Set(documents.data.items.map((item) => item.id));
  const linkable =
    others === null
      ? []
      : others.data.items
          .filter((item) => !linkedIds.has(item.id) && !alreadyLinked(item, context))
          .map((item) => ({ id: item.id, filename: item.filename }));
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
      context={context}
      contextHeading={heading}
      linkable={linkable}
    />
  );
}

function readContext(query: {
  appointment_id?: string;
  follow_up_id?: string;
}): DocumentContext | null {
  if (query.appointment_id !== undefined && query.appointment_id !== "") {
    return { kind: "visit", id: query.appointment_id };
  }
  if (query.follow_up_id !== undefined && query.follow_up_id !== "") {
    return { kind: "follow-up", id: query.follow_up_id };
  }
  return null;
}

function alreadyLinked(item: DocumentItem, context: DocumentContext | null): boolean {
  if (context?.kind === "visit") return item.appointment?.id === context.id;
  if (context?.kind === "follow-up") return item.follow_up?.id === context.id;
  return false;
}

async function contextHeading(
  cookieHeader: string,
  patientId: string,
  context: DocumentContext | null,
  items: DocumentItem[],
): Promise<string | null> {
  if (context === null) return null;
  if (context.kind === "follow-up") {
    const dueOn = items.find((item) => item.follow_up !== null)?.follow_up?.due_on;
    if (dueOn === undefined) return "Documents for this follow-up";
    return `Documents for the follow-up due ${formatDueOn(dueOn)}`;
  }
  const visit = await getAppointment(cookieHeader, context.id);
  if (!visit.ok || visit.data.patient.id !== patientId) return "Documents for this visit";
  const date = wallDate(visit.data.starts_at);
  const time = wallTime(visit.data.starts_at);
  const when = date === null || time === null ? "" : `, ${date} ${time}`;
  return `Documents for ${visit.data.appointment_type.name}${when}`;
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
