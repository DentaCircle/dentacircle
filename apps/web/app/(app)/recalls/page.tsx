import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { canUseRecallQueue } from "@/features/recalls/access";
import { noticeFromQuery, pageFromQuery, viewFromQuery } from "@/features/recalls/links";
import { QueueScreen, type QueueScreenProps } from "@/features/recalls/queue-screen";
import { listRecalls } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type RecallsPageProps = {
  searchParams: Promise<{ view?: string; page?: string; notice?: string }>;
};

export default async function RecallsPage({ searchParams }: RecallsPageProps) {
  const params = await searchParams;
  const user = await requireUser();
  const view = viewFromQuery(params.view);
  const page = pageFromQuery(params.page);
  const notice = noticeFromQuery(params.notice);
  if (!canUseRecallQueue(user.roles)) {
    return <QueueScreen {...emptyProps("forbidden", view, page, notice)} />;
  }
  const result = await listRecalls(await sessionCookieHeader(), page, view);
  return <QueueScreen {...viewProps(result, view, page, notice)} />;
}

function viewProps(
  result: Awaited<ReturnType<typeof listRecalls>>,
  view: QueueScreenProps["view"],
  page: number,
  notice: QueueScreenProps["notice"],
): QueueScreenProps {
  if (!result.ok) {
    const forbidden = result.error.kind === "api" && result.error.status === 403;
    return emptyProps(forbidden ? "forbidden" : "error", view, page, notice);
  }
  if (result.data.total === 0) {
    return { ...emptyProps("empty", view, page, notice), total: 0 };
  }
  return {
    status: "ready",
    view,
    notice,
    items: result.data.items.map((row) => ({
      id: row.id,
      status: row.status,
      dueOn: row.due_on,
      timing: row.timing,
      lastVisitOn: row.last_visit_on,
      recallType: row.recall_type.name,
      patient: {
        id: row.patient.id,
        displayId: row.patient.display_id,
        fullName: row.patient.full_name,
        phone: row.patient.phone,
      },
    })),
    total: result.data.total,
    page: result.data.page,
    pageSize: result.data.page_size,
  };
}

function emptyProps(
  status: "empty" | "forbidden" | "error",
  view: QueueScreenProps["view"],
  page: number,
  notice: QueueScreenProps["notice"],
): QueueScreenProps {
  return {
    status,
    items: [],
    total: 0,
    page,
    pageSize: 20,
    view,
    notice,
  };
}
