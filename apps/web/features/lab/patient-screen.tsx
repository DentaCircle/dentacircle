import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { AddLabForm } from "@/features/lab/add-form";
import { patientLabHref } from "@/features/lab/links";
import { LAB_NOTICES, type LabNotice } from "@/features/lab/notices";
import { type LabRow } from "@/features/lab/rows";
import { LabStatusActions } from "@/features/lab/status-actions";

export type PatientLabScreenProps = {
  status: "ready" | "empty" | "not-found" | "forbidden" | "error";
  patientId: string;
  rows: LabRow[];
  page: number;
  pageSize: number;
  total: number;
  isPatientInactive: boolean;
  notice: LabNotice | null;
};

export function PatientLabScreen({
  status,
  patientId,
  rows,
  page,
  pageSize,
  total,
  isPatientInactive,
  notice,
}: PatientLabScreenProps) {
  const isLoaded = status === "ready" || status === "empty";
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Lab</h1>
        <Link href={`/patients/${patientId}`}>Patient</Link>
      </div>
      {notice === null ? null : <p role="status">{LAB_NOTICES[notice]}</p>}
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Lab work could not be loaded.</p> : null}
      {isLoaded && isPatientInactive ? (
        <p>This patient is inactive, so lab work cannot be added.</p>
      ) : null}
      {isLoaded && !isPatientInactive ? <AddLabForm patientId={patientId} /> : null}
      {status === "empty" ? <p>No lab work for this patient yet.</p> : null}
      {status === "ready" ? (
        <ul className="flex flex-col gap-4">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-col gap-1 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{row.title}</span>
                <Badge variant="outline">{row.statusLabel}</Badge>
                {row.overdue ? <Badge variant="destructive">Overdue</Badge> : null}
              </div>
              <p>Expected {row.expectedOn}</p>
              {row.visit === null ? null : <p>{row.visit}</p>}
              <p>Added by {row.addedBy}</p>
              <p className="flex flex-wrap items-center gap-3">
                <Link href={row.documentsHref}>Documents</Link>
                <LabStatusActions
                  labWorkId={row.id}
                  status={row.status}
                  returnTo={{ kind: "patient", patientId, page }}
                />
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {status === "ready" ? (
        <nav aria-label="Pages" className="flex gap-3">
          {page > 1 ? (
            <Link href={patientLabHref(patientId, page - 1)}>Previous</Link>
          ) : (
            <span>Previous</span>
          )}
          {page * pageSize < total ? (
            <Link href={patientLabHref(patientId, page + 1)}>Next</Link>
          ) : (
            <span>Next</span>
          )}
        </nav>
      ) : null}
    </section>
  );
}
