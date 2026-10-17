import { canReadCare, canWriteCare } from "@/features/care/access";
import {
  CareSessionScreen,
  type CareSessionScreenProps,
  type VisitSummary,
} from "@/features/care-session/care-session-screen";
import { isSessionNotice } from "@/features/care-session/notices";
import type { OpenCarePlan } from "@/features/care-session/session-form";
import { wallTime } from "@/features/appointments/wall-time";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { getAppointment, getCareSession, listCarePlans, type CarePlan } from "@/lib/api/client";

export const dynamic = "force-dynamic";

const RECORDABLE = new Set(["arrived", "in_progress"]);

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ notice?: string }>;
};

export default async function CareSessionPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  const notice = isSessionNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canReadCare(user.roles)) {
    return <CareSessionScreen {...empty(id, "forbidden")} notice={null} />;
  }
  const cookie = await sessionCookieHeader();
  const visit = await getAppointment(cookie, id);
  if (!visit.ok) {
    return <CareSessionScreen {...failure(id, visit.error)} notice={null} />;
  }
  const recorded = await getCareSession(cookie, id);
  if (!recorded.ok) {
    return <CareSessionScreen {...failure(id, recorded.error)} notice={null} />;
  }
  const summary = visitSummary(visit.data);
  if (summary === null) {
    return <CareSessionScreen {...empty(id, "error")} notice={null} />;
  }
  const session = recorded.data.session;
  const canRecord = canWriteCare(user.roles) && session === null && RECORDABLE.has(summary.status);
  let openPlans: OpenCarePlan[] = [];
  if (canRecord) {
    const plans = await listCarePlans(cookie, summary.patientId);
    if (!plans.ok) {
      return <CareSessionScreen {...failure(id, plans.error)} notice={null} />;
    }
    openPlans = openItems(plans.data);
  }
  return (
    <CareSessionScreen
      status="ready"
      appointmentId={id}
      visit={summary}
      session={session}
      openPlans={openPlans}
      canRecord={canRecord}
      notice={notice}
    />
  );
}

function visitSummary(visit: {
  starts_at: string;
  ends_at: string;
  status: string;
  patient: { id: string; full_name: string };
}): VisitSummary | null {
  const start = wallTime(visit.starts_at);
  const end = wallTime(visit.ends_at);
  if (start === null || end === null) return null;
  return {
    patientId: visit.patient.id,
    patientName: visit.patient.full_name,
    timeRange: `${start}–${end}`,
    status: visit.status,
  };
}

function openItems(plans: CarePlan[]): OpenCarePlan[] {
  return plans.flatMap((plan) => {
    const items = plan.items.flatMap((item) => {
      if (item.status !== "planned" && item.status !== "started") return [];
      return [{ id: item.id, name: item.name, status: item.status }];
    });
    if (items.length === 0) return [];
    return [{ id: plan.id, title: plan.title, items }];
  });
}

function empty(
  appointmentId: string,
  status: CareSessionScreenProps["status"],
): Omit<CareSessionScreenProps, "notice"> {
  return {
    status,
    appointmentId,
    visit: null,
    session: null,
    openPlans: [],
    canRecord: false,
  };
}

function failure(
  appointmentId: string,
  error: { kind: string; status?: number },
): Omit<CareSessionScreenProps, "notice"> {
  if (error.kind === "api" && error.status === 403) return empty(appointmentId, "forbidden");
  if (error.kind === "api" && error.status === 404) return empty(appointmentId, "not-found");
  return empty(appointmentId, "error");
}
