import { wallDate, wallTime } from "@/features/appointments/wall-time";
import { formatDueOn } from "@/features/care/follow-up-line";
import { visitLinkText } from "@/features/documents/links";
import { labDocumentsHref } from "@/features/lab/links";
import type { LabWorkItem, LabWorkStatus } from "@/lib/api/client";

export const LAB_STATUS_LABELS: Record<LabWorkStatus, string> = {
  pending: "Pending",
  ready: "Ready",
  collected: "Collected",
  cancelled: "Cancelled",
};

export type LabRow = {
  id: string;
  title: string;
  status: LabWorkStatus;
  statusLabel: string;
  expectedOn: string;
  overdue: boolean;
  visit: string | null;
  addedBy: string;
  documentsHref: string;
  patient: { id: string; displayId: string; fullName: string };
};

export function labRow(item: LabWorkItem): LabRow {
  const date = wallDate(item.created_at);
  const time = wallTime(item.created_at);
  const when = date === null || time === null ? "—" : `${date} ${time}`;
  return {
    id: item.id,
    title: item.title,
    status: item.status,
    statusLabel: LAB_STATUS_LABELS[item.status],
    expectedOn: item.expected_on === null ? "—" : formatDueOn(item.expected_on),
    overdue: item.overdue,
    visit: item.appointment === null ? null : visitLinkText(item.appointment),
    addedBy: `${item.created_by.name}, ${when}`,
    documentsHref: labDocumentsHref(item.patient.id, item.id),
    patient: {
      id: item.patient.id,
      displayId: item.patient.display_id,
      fullName: item.patient.full_name,
    },
  };
}
