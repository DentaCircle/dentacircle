import Link from "next/link";

import { timelineHref } from "@/features/timeline/links";

export type TimelineEntry = {
  id: string;
  time: string;
  sentence: string;
  actorName: string;
  href: string | null;
};

export type TimelineDayGroup = {
  date: string;
  heading: string;
  entries: TimelineEntry[];
};

export type TimelineScreenProps = {
  status: "ready" | "empty" | "not-found" | "forbidden" | "error";
  patientId: string;
  days: TimelineDayGroup[];
  page: number;
  pageSize: number;
  total: number;
};

export function TimelineScreen({
  status,
  patientId,
  days,
  page,
  pageSize,
  total,
}: TimelineScreenProps) {
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Timeline</h1>
        <Link href={`/patients/${patientId}`}>Patient</Link>
      </div>
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Timeline could not be loaded.</p> : null}
      {status === "empty" ? <p>Nothing has happened for this patient yet.</p> : null}
      {status === "ready"
        ? days.map((day) => (
            <section key={day.date} className="flex flex-col gap-2">
              <h2 className="font-semibold">{day.heading}</h2>
              <ul className="flex flex-col gap-3">
                {day.entries.map((entry) => (
                  <li key={entry.id} className="text-sm">
                    <p>{entry.time}</p>
                    {entry.href === null ? (
                      <p>{entry.sentence}</p>
                    ) : (
                      <p>
                        <Link href={entry.href}>{entry.sentence}</Link>
                      </p>
                    )}
                    <p>{entry.actorName}</p>
                  </li>
                ))}
              </ul>
            </section>
          ))
        : null}
      {status === "ready" ? (
        <nav aria-label="Pages" className="flex gap-3">
          {page > 1 ? (
            <Link href={timelineHref(patientId, page - 1)}>Previous</Link>
          ) : (
            <span>Previous</span>
          )}
          {page * pageSize < total ? (
            <Link href={timelineHref(patientId, page + 1)}>Next</Link>
          ) : (
            <span>Next</span>
          )}
        </nav>
      ) : null}
    </section>
  );
}
