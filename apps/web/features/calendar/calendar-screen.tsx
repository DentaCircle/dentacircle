import { CalendarControls, type ClinicianOption } from "@/features/calendar/controls";
import { DaySection, type CalendarDay } from "@/features/calendar/day-section";
import { CALENDAR_NOTICES, calendarHref, type CalendarNotice, type CalendarViewMode } from "@/features/calendar/links";

export type CalendarScreenProps =
  | { status: "forbidden" | "error" }
  | {
      status: "ready";
      view: CalendarViewMode;
      date: string;
      today: string;
      clinician: string | null;
      clinicians: ClinicianOption[];
      days: CalendarDay[];
      notice: CalendarNotice | null;
      canAdvance: boolean;
    };

export function CalendarScreen(props: CalendarScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Calendar</h1>
      {props.status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {props.status === "error" ? <p role="alert">Something went wrong.</p> : null}
      {props.status === "ready" ? (
        <>
          {props.notice === null ? null : <p role="status">{CALENDAR_NOTICES[props.notice]}</p>}
          <CalendarControls
            view={props.view}
            date={props.date}
            today={props.today}
            clinician={props.clinician}
            clinicians={props.clinicians}
          />
          {props.days.map((day) => (
            <DaySection
              key={day.date}
              day={day}
              canAdvance={props.canAdvance}
              returnHref={calendarHref({
                view: props.view,
                date: props.date,
                clinician: props.clinician,
              })}
            />
          ))}
        </>
      ) : null}
    </section>
  );
}
