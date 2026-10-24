import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { clinicLabHref, patientLabHref } from "@/features/lab/links";
import { LAB_NOTICES, type LabNotice } from "@/features/lab/notices";
import { type LabRow } from "@/features/lab/rows";
import { LabStatusActions } from "@/features/lab/status-actions";
import type { LabWorkListView } from "@/lib/api/client";

export type ClinicLabScreenProps = {
  status: "ready" | "empty" | "forbidden" | "error";
  rows: LabRow[];
  total: number;
  page: number;
  pageSize: number;
  view: LabWorkListView;
  notice: LabNotice | null;
};

export function ClinicLabScreen({
  status,
  rows,
  total,
  page,
  pageSize,
  view,
  notice,
}: ClinicLabScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Lab</h1>
      {notice === null ? null : <p role="status">{LAB_NOTICES[notice]}</p>}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Lab work could not be loaded.</p> : null}
      {status === "forbidden" ? null : <ViewLinks view={view} />}
      {status === "empty" ? (
        <p>{view === "open" ? "No lab work is open." : "No lab work."}</p>
      ) : null}
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
                  Title
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Expected
                </th>
                <th className="py-2 font-medium" scope="col">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b">
                  <td className="py-2 pr-3">
                    <Link href={patientLabHref(row.patient.id)} className="font-medium underline">
                      {row.patient.fullName}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge>{row.patient.displayId}</Badge>
                  </td>
                  <td className="py-2 pr-3">{row.title}</td>
                  <td className="py-2 pr-3">
                    <span className="inline-flex flex-wrap items-center gap-2">
                      {row.expectedOn}
                      {row.overdue ? <Badge variant="destructive">Overdue</Badge> : null}
                    </span>
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span>{row.statusLabel}</span>
                      <Link href={row.documentsHref}>Documents</Link>
                      <LabStatusActions
                        labWorkId={row.id}
                        status={row.status}
                        returnTo={{ kind: "clinic", view, page }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav aria-label="Pages" className="flex gap-3">
            {page > 1 ? (
              <Link href={clinicLabHref(view, page - 1)}>Previous</Link>
            ) : (
              <span>Previous</span>
            )}
            {page * pageSize < total ? (
              <Link href={clinicLabHref(view, page + 1)}>Next</Link>
            ) : (
              <span>Next</span>
            )}
          </nav>
        </>
      ) : null}
    </section>
  );
}

function ViewLinks({ view }: { view: LabWorkListView }) {
  return (
    <nav aria-label="Lab views" className="flex gap-3 text-sm">
      <Link href={clinicLabHref("open")} aria-current={view === "open" ? "page" : undefined}>
        Open
      </Link>
      <Link href={clinicLabHref("all")} aria-current={view === "all" ? "page" : undefined}>
        All
      </Link>
    </nav>
  );
}
