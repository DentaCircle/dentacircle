import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { ContactedButton } from "@/features/follow-ups/contacted-button";
import { followUpsHref, noticeText, type QueueNotice } from "@/features/follow-ups/links";
import { formatDueOn } from "@/features/care/follow-up-line";
import type { FollowUpQueueView, FollowUpStatus, FollowUpTiming } from "@/lib/api/client";

export type QueueRow = {
  id: string;
  status: FollowUpStatus;
  dueOn: string;
  timing: FollowUpTiming;
  patient: { id: string; displayId: string; fullName: string; phone: string };
};

export type QueueScreenProps = {
  status: "ready" | "empty" | "forbidden" | "error";
  items: QueueRow[];
  total: number;
  page: number;
  pageSize: number;
  view: FollowUpQueueView;
  notice: QueueNotice | null;
};

const TIMING_LABELS: Record<FollowUpTiming, string> = {
  overdue: "Overdue",
  due_today: "Due today",
  upcoming: "Upcoming",
};

const STATUS_LABELS: Record<FollowUpStatus, string> = {
  scheduled: "Scheduled",
  contacted: "Contacted",
  booked: "Booked",
};

const TIMING_VARIANT: Record<FollowUpTiming, "destructive" | "default" | "secondary"> = {
  overdue: "destructive",
  due_today: "default",
  upcoming: "secondary",
};

export function QueueScreen({
  status,
  items,
  total,
  page,
  pageSize,
  view,
  notice,
}: QueueScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Follow-ups</h1>
      {notice === null ? null : <p role="status">{noticeText(notice)}</p>}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Follow-ups could not be loaded.</p> : null}
      {status === "forbidden" ? null : <ViewLinks view={view} />}
      {status === "empty" ? <p>No follow-ups are due.</p> : null}
      {status === "ready" ? (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium" scope="col">
                  Name
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  ID
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Phone
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Due
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Timing
                </th>
                <th className="py-2 font-medium" scope="col">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id} className="border-b">
                  <td className="py-2 pr-3">
                    <Link href={`/patients/${row.patient.id}`} className="font-medium underline">
                      {row.patient.fullName}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge>{row.patient.displayId}</Badge>
                  </td>
                  <td className="py-2 pr-3">{row.patient.phone}</td>
                  <td className="py-2 pr-3">{formatDueOn(row.dueOn)}</td>
                  <td className="py-2 pr-3">
                    <Badge variant={TIMING_VARIANT[row.timing]}>{TIMING_LABELS[row.timing]}</Badge>
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span>{STATUS_LABELS[row.status]}</span>
                      {row.status === "scheduled" ? (
                        <ContactedButton followUpId={row.id} view={view} page={page} />
                      ) : null}
                      {row.status === "scheduled" || row.status === "contacted" ? (
                        <Link href={`/follow-ups/${row.id}/book`}>Book visit</Link>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav aria-label="Pages" className="flex gap-3">
            {page > 1 ? (
              <Link href={followUpsHref(view, page - 1)}>Previous</Link>
            ) : (
              <span>Previous</span>
            )}
            {page * pageSize < total ? (
              <Link href={followUpsHref(view, page + 1)}>Next</Link>
            ) : (
              <span>Next</span>
            )}
          </nav>
        </>
      ) : null}
    </section>
  );
}

function ViewLinks({ view }: { view: FollowUpQueueView }) {
  return (
    <nav aria-label="View" className="flex gap-3 text-sm">
      <Link href={followUpsHref("due", 1)} aria-current={view === "due" ? "page" : undefined}>
        Due
      </Link>
      <Link href={followUpsHref("all", 1)} aria-current={view === "all" ? "page" : undefined}>
        All open
      </Link>
    </nav>
  );
}
