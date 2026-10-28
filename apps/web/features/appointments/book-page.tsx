import Link from "next/link";

import { BookScreen, type BookChoice } from "@/features/appointments/book-screen";

export type BookPageProps =
  | { status: "forbidden" | "not-found" | "error" | "inactive" | "no-clinicians" | "no-types" }
  | {
      status: "ready";
      patientId: string;
      patient: { full_name: string; display_id: string };
      types: BookChoice[];
      clinicians: BookChoice[];
      today: string;
    };

export function BookPage(props: BookPageProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Book appointment</h1>
        {props.status === "ready" ? <Link href={`/patients/${props.patientId}`}>Patient</Link> : null}
      </div>
      {props.status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {props.status === "not-found" ? <p role="alert">Patient not found</p> : null}
      {props.status === "inactive" ? <p role="alert">This patient is inactive.</p> : null}
      {props.status === "no-clinicians" ? <p>No clinicians are set up.</p> : null}
      {props.status === "no-types" ? <p>No appointment types are set up.</p> : null}
      {props.status === "error" ? <p role="alert">Something went wrong.</p> : null}
      {props.status === "ready" ? (
        <BookScreen
          patient={props.patient}
          patientId={props.patientId}
          types={props.types}
          clinicians={props.clinicians}
          today={props.today}
          submitUrl="/api/appointments"
          doneUrl={`/patients/${props.patientId}?booked=1`}
        />
      ) : null}
    </section>
  );
}
