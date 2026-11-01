import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CancelButton } from "@/features/calendar/cancel-button";
import { StatusButton } from "@/features/calendar/status-button";

const STATUS_LABELS: Record<string, string> = {
  arrived: "Arrived",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No-show",
};

export type AppointmentRowProps = {
  id: string;
  timeRange: string;
  patientId: string;
  patientName: string;
  displayId: string;
  typeName: string;
  clinicianName: string;
  status: string;
  canAdvance: boolean;
  returnHref: string;
};

export function AppointmentRow({
  timeRange,
  patientId,
  patientName,
  displayId,
  typeName,
  clinicianName,
  status,
  canAdvance,
  id,
  returnHref,
}: AppointmentRowProps) {
  const statusLabel = status === "scheduled" ? null : (STATUS_LABELS[status] ?? status);
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 border-b py-4 text-sm">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{timeRange}</span>
          <Link className="font-medium underline" href={`/patients/${patientId}`}>{patientName}</Link>
          <span>{displayId}</span>
          {statusLabel === null ? <Badge variant="secondary">Scheduled</Badge> : <Badge variant="secondary">{statusLabel}</Badge>}
        </div>
        <p>{typeName} · {clinicianName}</p>
      </div>
      <div role="group" aria-label="Visit actions" className="flex flex-wrap items-start gap-2">
        {status === "scheduled" ? <StatusButton appointmentId={id} returnHref={returnHref} target="arrived" /> : null}
        {status === "arrived" && canAdvance ? (
          <StatusButton appointmentId={id} returnHref={returnHref} target="in_progress" />
        ) : null}
        {status === "in_progress" && canAdvance ? (
          <StatusButton appointmentId={id} returnHref={returnHref} target="completed" />
        ) : null}
        {status === "scheduled" ? (
          <>
            <StatusButton appointmentId={id} returnHref={returnHref} target="no_show" />
            <Button asChild variant="outline" size="sm"><Link href={`/appointments/${id}/reschedule`}>Reschedule</Link></Button>
            <CancelButton appointmentId={id} returnHref={returnHref} />
          </>
        ) : null}
        {status === "arrived" || status === "in_progress" || status === "completed" ? (
          <Button asChild variant="outline" size="sm"><Link href={`/appointments/${id}/care`}>Care session</Link></Button>
        ) : null}
        <Button asChild variant="outline" size="sm"><Link href={`/patients/${patientId}/documents?appointment_id=${id}`}>Documents</Link></Button>
      </div>
    </li>
  );
}
