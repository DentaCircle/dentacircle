import { canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { canUseFollowUpQueue } from "@/features/follow-ups/access";
import { FollowUpBookPage } from "@/features/follow-ups/book-page";
import { sessionCookieHeader } from "@/features/patients/session";
import {
  getClinicDay,
  listAppointmentTypes,
  listClinicians,
  listFollowUps,
  type FollowUpQueueItem,
} from "@/lib/api/client";

export const dynamic = "force-dynamic";

type FollowUpBookRouteProps = {
  params: Promise<{ id: string }>;
};

export default async function FollowUpBookRoute({ params }: FollowUpBookRouteProps) {
  const { id } = await params;
  const user = await requireUser();
  if (!canUseFollowUpQueue(user.roles) || !canBookAppointments(user.roles)) {
    return <FollowUpBookPage status="forbidden" />;
  }
  const cookie = await sessionCookieHeader();
  const found = await findQueueItem(cookie, id);
  if (found === "forbidden") return <FollowUpBookPage status="forbidden" />;
  if (found === "error") return <FollowUpBookPage status="error" />;
  if (found === null || found.status === "booked") {
    return <FollowUpBookPage status="closed" />;
  }
  const [clinicians, types, day] = await Promise.all([
    listClinicians(cookie),
    listAppointmentTypes(cookie),
    getClinicDay(cookie),
  ]);
  if (!clinicians.ok || !types.ok || !day.ok) return <FollowUpBookPage status="error" />;
  if (clinicians.data.length === 0) return <FollowUpBookPage status="no-clinicians" />;
  if (types.data.length === 0) return <FollowUpBookPage status="no-types" />;
  let today: string;
  try {
    today = clinicToday(day.data.timezone);
  } catch {
    return <FollowUpBookPage status="error" />;
  }
  return (
    <FollowUpBookPage
      status="ready"
      followUpId={found.id}
      today={today}
      clinicians={clinicians.data.map((row) => ({ id: row.id, label: row.full_name }))}
      types={types.data.map((row) => ({ id: row.id, label: row.name }))}
    />
  );
}

async function findQueueItem(
  cookie: string,
  followUpId: string,
): Promise<FollowUpQueueItem | null | "error" | "forbidden"> {
  let page = 1;
  for (;;) {
    const listed = await listFollowUps(cookie, page, "all", 100);
    if (!listed.ok) {
      if (listed.error.kind === "api" && listed.error.status === 403) return "forbidden";
      return "error";
    }
    const match = listed.data.items.find((item) => item.id === followUpId);
    if (match !== undefined) return match;
    if (listed.data.items.length === 0 || page * listed.data.page_size >= listed.data.total) {
      return null;
    }
    page += 1;
  }
}
