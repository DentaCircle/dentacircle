import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { SESSION_NOTICES, type SessionNotice } from "@/features/care-session/notices";
import { SessionForm, type OpenCarePlan } from "@/features/care-session/session-form";
import type { CareSession } from "@/lib/api/client";

const VISIT_LABELS: Record<string, string> = {
  scheduled: "Scheduled",
  arrived: "Arrived",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No-show",
};

const ITEM_LABELS = { started: "Started", completed: "Completed" } as const;

export type VisitSummary = {
  patientId: string;
  patientName: string;
  timeRange: string;
  status: string;
};

export type CareSessionScreenProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  appointmentId: string;
  visit: VisitSummary | null;
  session: CareSession | null;
  openPlans: OpenCarePlan[];
  canRecord: boolean;
  notice: SessionNotice | null;
};

export function CareSessionScreen({
  status,
  appointmentId,
  visit,
  session,
  openPlans,
  canRecord,
  notice,
}: CareSessionScreenProps) {
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <h1 className="text-2xl font-semibold">Care session</h1>
      {notice === null ? null : <p role="status">{SESSION_NOTICES[notice]}</p>}
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Care session could not be loaded.</p> : null}
      {status === "ready" && visit !== null ? <Visit visit={visit} /> : null}
      {status === "ready" && session !== null ? <Recorded session={session} /> : null}
      {status === "ready" && session === null && canRecord && openPlans.length > 0 ? (
        <SessionForm appointmentId={appointmentId} plans={openPlans} />
      ) : null}
      {status === "ready" && session === null && canRecord && openPlans.length === 0 ? (
        <p>
          No open care items.{" "}
          <Link href={`/patients/${visit?.patientId ?? ""}/care`}>Care</Link>
        </p>
      ) : null}
      {status === "ready" && session === null && !canRecord ? <p>No care session recorded.</p> : null}
    </section>
  );
}

function Visit({ visit }: { visit: VisitSummary }) {
  const label = VISIT_LABELS[visit.status] ?? visit.status;
  return (
    <p className="flex flex-wrap items-center gap-2">
      <Link href={`/patients/${visit.patientId}`}>{visit.patientName}</Link>
      <span>{visit.timeRange}</span>
      <Badge variant="secondary">{label}</Badge>
    </p>
  );
}

function Recorded({ session }: { session: CareSession }) {
  return (
    <div className="flex flex-col gap-2">
      <p>Recorded by {session.recorded_by_name}</p>
      <ul className="flex flex-col gap-2">
        {session.items.map((item) => (
          <li key={item.care_item_id}>
            {item.plan_title}: {item.name} <Badge variant="secondary">{ITEM_LABELS[item.status]}</Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
