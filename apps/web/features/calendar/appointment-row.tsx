import Link from "next/link";

import { Badge } from "@/components/ui/badge";

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
};

export function AppointmentRow({
  timeRange,
  patientId,
  patientName,
  displayId,
  typeName,
  clinicianName,
  status,
}: AppointmentRowProps) {
  const statusLabel = status === "scheduled" ? null : (STATUS_LABELS[status] ?? status);
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b py-2 text-sm">
      <span className="font-medium">{timeRange}</span>
      <Link href={`/patients/${patientId}`}>{patientName}</Link>
      <span>{displayId}</span>
      <span>{typeName}</span>
      <span>{clinicianName}</span>
      {statusLabel === null ? null : <Badge variant="secondary">{statusLabel}</Badge>}
    </li>
  );
}
