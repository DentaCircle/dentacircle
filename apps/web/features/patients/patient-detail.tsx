import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PatientStatusButton, statusLabel } from "@/features/patients/patient-status-button";

export type PatientDetailData = {
  id: string;
  displayId: string;
  fullName: string;
  phone: string;
  dateOfBirth: string | null;
  status: "active" | "inactive";
  registeredOn: string;
};

export type UpcomingAppointment = {
  id: string;
  date: string;
  time: string;
  typeName: string;
  clinicianName: string;
};

export type PatientDetailProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  patient: PatientDetailData | null;
  canEdit: boolean;
  canBook: boolean;
  saved: boolean;
  booked: boolean;
  upcomingItems: UpcomingAppointment[] | null;
};

export function PatientDetail({
  status,
  patient,
  canEdit,
  canBook,
  saved,
  booked,
  upcomingItems,
}: PatientDetailProps) {
  return (
    <section className="flex max-w-lg flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">
          {status === "ready" && patient !== null ? patient.fullName : "Patient"}
        </h1>
        <div className="flex gap-3 text-sm">
          {status === "ready" && patient !== null && canBook && patient.status === "active" ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/patients/${patient.id}/book`}>Book appointment</Link>
            </Button>
          ) : null}
          {status === "ready" && patient !== null && canEdit ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/patients/${patient.id}/edit`}>Edit</Link>
            </Button>
          ) : null}
          <Link href="/patients">Patients</Link>
        </div>
      </div>
      {saved ? <p role="status">Saved.</p> : null}
      {booked ? <p role="status">Booked.</p> : null}
      {status === "not-found" ? <p role="alert">Patient not found</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">The patient could not be loaded.</p> : null}
      {status === "ready" && patient !== null ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <dt>ID</dt>
          <dd>
            <Badge>{patient.displayId}</Badge>
          </dd>
          <dt>Name</dt>
          <dd>{patient.fullName}</dd>
          <dt>Phone</dt>
          <dd>{patient.phone}</dd>
          <dt>Date of birth</dt>
          <dd>{patient.dateOfBirth ?? "—"}</dd>
          <dt>Status</dt>
          <dd>
            {canEdit ? (
              <PatientStatusButton patientId={patient.id} status={patient.status} />
            ) : (
              statusLabel(patient.status)
            )}
          </dd>
          <dt>Registered</dt>
          <dd>{patient.registeredOn}</dd>
        </dl>
      ) : null}
      {status === "ready" && patient !== null ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">Upcoming appointments</h2>
          {upcomingItems === null ? <p role="alert">Something went wrong.</p> : null}
          {upcomingItems !== null && upcomingItems.length === 0 ? <p>No upcoming appointments.</p> : null}
          {upcomingItems !== null && upcomingItems.length > 0 ? (
            <ul className="flex flex-col gap-2 text-sm">
              {upcomingItems.map((item) => (
                <li key={item.id}>
                  {item.date} {item.time} {item.typeName} {item.clinicianName}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

export function registeredOn(createdAt: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(createdAt);
  return match === null ? "—" : match[1];
}
