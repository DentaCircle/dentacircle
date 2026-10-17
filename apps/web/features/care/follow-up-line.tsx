import { Badge } from "@/components/ui/badge";
import type { FollowUp, FollowUpStatus } from "@/lib/api/client";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const STATUS_LABELS: Record<FollowUpStatus, string> = {
  scheduled: "Scheduled",
  contacted: "Contacted",
  booked: "Booked",
};

export function formatDueOn(dueOn: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(dueOn);
  if (match === null) return dueOn;
  const month = MONTHS[Number(match[2]) - 1];
  if (month === undefined) return dueOn;
  return `${Number(match[3])} ${month} ${match[1]}`;
}

export function FollowUpLine({ followUp }: { followUp: FollowUp }) {
  return (
    <p className="flex flex-wrap items-center gap-2">
      <span>Follow-up due {formatDueOn(followUp.due_on)}</span>
      <Badge>{STATUS_LABELS[followUp.status]}</Badge>
    </p>
  );
}
