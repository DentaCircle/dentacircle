import { requireUser } from "@/features/auth/current-user";
import { canUseDocuments } from "@/features/documents/access";
import { documentRow } from "@/features/documents/rows";
import { ViewerScreen, type ViewerScreenProps } from "@/features/documents/viewer-screen";
import { sessionCookieHeader } from "@/features/patients/session";
import { getDocument } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type ViewerPageProps = {
  params: Promise<{ id: string; documentId: string }>;
};

export default async function ViewerPage({ params }: ViewerPageProps) {
  const { id, documentId } = await params;
  const user = await requireUser();
  if (!canUseDocuments(user.roles)) {
    return <ViewerScreen {...blank("forbidden", id)} />;
  }
  const found = await getDocument(await sessionCookieHeader(), id, documentId);
  if (!found.ok) return <ViewerScreen {...failure(found.error, id)} />;
  return <ViewerScreen status="ready" patientId={id} row={documentRow(id, found.data)} />;
}

function failure(error: { kind: string; status?: number }, patientId: string): ViewerScreenProps {
  if (error.kind === "api" && error.status === 403) return blank("forbidden", patientId);
  if (error.kind === "api" && error.status === 404) return blank("not-found", patientId);
  return blank("error", patientId);
}

function blank(status: "not-found" | "forbidden" | "error", patientId: string): ViewerScreenProps {
  return { status, patientId, row: null };
}
