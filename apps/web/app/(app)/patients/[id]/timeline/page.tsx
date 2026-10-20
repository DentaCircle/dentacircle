import { wallTime } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { canReadTimeline } from "@/features/timeline/access";
import { groupByDay } from "@/features/timeline/group";
import { entryHref, pageFromQuery } from "@/features/timeline/links";
import { entrySentence } from "@/features/timeline/sentences";
import {
  TimelineScreen,
  type TimelineDayGroup,
  type TimelineScreenProps,
} from "@/features/timeline/timeline-screen";
import { listTimeline, type TimelineItem } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type TimelinePageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
};

export default async function TimelinePage({ params, searchParams }: TimelinePageProps) {
  const { id } = await params;
  const query = await searchParams;
  const page = pageFromQuery(query.page);
  const user = await requireUser();
  if (!canReadTimeline(user.roles)) {
    return <TimelineScreen {...emptyProps("forbidden", id, page)} />;
  }
  const result = await listTimeline(await sessionCookieHeader(), id, page);
  if (!result.ok) return <TimelineScreen {...failureProps(result.error, id, page)} />;
  if (result.data.total === 0) {
    return <TimelineScreen {...emptyProps("empty", id, page)} />;
  }
  return (
    <TimelineScreen
      status="ready"
      patientId={id}
      days={daysFrom(id, result.data.items)}
      page={result.data.page}
      pageSize={result.data.page_size}
      total={result.data.total}
    />
  );
}

function daysFrom(patientId: string, items: TimelineItem[]): TimelineDayGroup[] {
  return groupByDay(items).map((day) => ({
    date: day.date,
    heading: day.heading,
    entries: day.items.map((item) => ({
      id: item.id,
      time: wallTime(item.occurred_at) ?? "",
      sentence: entrySentence(item),
      actorName: item.actor.name,
      href: entryHref(patientId, item),
    })),
  }));
}

function failureProps(
  error: { kind: string; status?: number },
  patientId: string,
  page: number,
): TimelineScreenProps {
  const forbidden = error.kind === "api" && error.status === 403;
  const missing = error.kind === "api" && error.status === 404;
  if (forbidden) return emptyProps("forbidden", patientId, page);
  if (missing) return emptyProps("not-found", patientId, page);
  return emptyProps("error", patientId, page);
}

function emptyProps(
  status: "empty" | "not-found" | "forbidden" | "error",
  patientId: string,
  page: number,
): TimelineScreenProps {
  return {
    status,
    patientId,
    days: [],
    page,
    pageSize: 20,
    total: 0,
  };
}
