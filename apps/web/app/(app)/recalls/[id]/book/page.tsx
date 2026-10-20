import { canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { canUseRecallQueue } from "@/features/recalls/access";
import { RecallBookPage } from "@/features/recalls/book-page";
import {
  getClinicDay,
  listAppointmentTypes,
  listClinicians,
  listRecalls,
  type RecallQueueItem,
} from "@/lib/api/client";

export const dynamic = "force-dynamic";

type RecallBookRouteProps = {
  params: Promise<{ id: string }>;
};

export default async function RecallBookRoute({ params }: RecallBookRouteProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canUseRecallQueue(user.roles) || !canBookAppointments(user.roles)) {
    return <RecallBookPage status="forbidden" />;
  }
  const cookie = await sessionCookieHeader();
  const found = await findQueueItem(cookie, id);
  if (found === "forbidden") return <RecallBookPage status="forbidden" />;
  if (found === "error") return <RecallBookPage status="error" />;
  if (found === null || found.status === "booked") {
    return <RecallBookPage status="closed" />;
  }
  const [clinicians, types, day] = await Promise.all([
    listClinicians(cookie),
    listAppointmentTypes(cookie),
    getClinicDay(cookie),
  ]);
  if (!clinicians.ok || !types.ok || !day.ok) return <RecallBookPage status="error" />;
  if (clinicians.data.length === 0) return <RecallBookPage status="no-clinicians" />;
  if (types.data.length === 0) return <RecallBookPage status="no-types" />;
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <RecallBookPage status="error" />;
  }
  return (
    <RecallBookPage
      status="ready"
      recallId={found.id}
      today={today}
      clinicians={clinicians.data.map((row) => ({ id: row.id, label: row.full_name }))}
      types={types.data.map((row) => ({ id: row.id, label: row.name }))}
    />
  );
}

async function findQueueItem(
  cookie: string,
  recallId: string,
): Promise<RecallQueueItem | null | "error" | "forbidden"> {
  let page = 1;
  for (;;) {
    const listed = await listRecalls(cookie, page, "all", 100);
    if (!listed.ok) {
      if (listed.error.kind === "api" && listed.error.status === 403) return "forbidden";
      return "error";
    }
    const match = listed.data.items.find((item) => item.id === recallId);
    if (match !== undefined) return match;
    if (listed.data.items.length === 0 || page * listed.data.page_size >= listed.data.total) {
      return null;
    }
    page += 1;
  }
}
