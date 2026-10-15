import { RescheduleScreen } from "@/features/appointments/reschedule-screen";
import type { BookChoice } from "@/features/appointments/choice-field";

export type ReschedulePageProps =
  | { status: "forbidden" | "not-found" | "error" | "not-scheduled" }
  | {
      status: "ready";
      appointmentId: string;
      patientName: string;
      typeName: string;
      currentWhen: string;
      clinicians: BookChoice[];
      initialClinicianId: string;
      initialDate: string;
      today: string;
    };

export function ReschedulePage(props: ReschedulePageProps) {
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Reschedule</h1>
      {props.status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {props.status === "not-found" ? <p role="alert">Appointment not found</p> : null}
      {props.status === "not-scheduled" ? (
        <p role="alert">This appointment can no longer be moved.</p>
      ) : null}
      {props.status === "error" ? <p role="alert">Something went wrong.</p> : null}
      {props.status === "ready" ? (
        <>
          <p>
            {props.patientName}, {props.typeName}, {props.currentWhen}
          </p>
          <RescheduleScreen
            appointmentId={props.appointmentId}
            clinicians={props.clinicians}
            initialClinicianId={props.initialClinicianId}
            initialDate={props.initialDate}
            today={props.today}
          />
        </>
      ) : null}
    </section>
  );
}
