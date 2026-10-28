import type { ReactNode } from "react";
import Link from "next/link";

export type PatientSection = "overview" | "care" | "documents" | "lab" | "timeline";
export type PatientIdentity = { id: string; full_name: string; display_id: string };

const sections: { label: string; section: PatientSection; suffix: string }[] = [
  { label: "Overview", section: "overview", suffix: "" },
  { label: "Care", section: "care", suffix: "/care" },
  { label: "Documents", section: "documents", suffix: "/documents" },
  { label: "Lab", section: "lab", suffix: "/lab" },
  { label: "Timeline", section: "timeline", suffix: "/timeline" },
];

export function PatientNavigation({ patientId, current }: { patientId: string; current: PatientSection }) {
  return (
    <nav aria-label="Patient sections" className="flex flex-wrap gap-x-5 gap-y-2 border-b pb-3 text-sm">
      {sections.map(({ label, section, suffix }) => (
        <Link key={section} href={`/patients/${encodeURIComponent(patientId)}${suffix}`}
          aria-current={current === section ? "page" : undefined}
          className="rounded-md px-2 py-1 font-medium text-primary aria-[current=page]:bg-accent aria-[current=page]:font-semibold">
          {label}
        </Link>
      ))}
    </nav>
  );
}

export function PatientWorkspace({ patient, current, children }: {
  patient: PatientIdentity | null;
  current: PatientSection;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 max-w-4xl flex-col gap-5 rounded-xl border bg-card p-5 sm:p-7">
      {patient === null ? (
        <p role="alert">Patient details could not be loaded.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-3">
            <p className="text-lg font-semibold">{patient.full_name}</p>
            <span className="text-sm text-muted-foreground">{patient.display_id}</span>
          </div>
          <PatientNavigation patientId={patient.id} current={current} />
        </>
      )}
      {children}
    </div>
  );
}
