import { AppointmentRow, type AppointmentRowProps } from "@/features/calendar/appointment-row";

export type CalendarDay = {
  date: string;
  heading: string;
  isToday: boolean;
  visits: AppointmentRowProps[];
};

export function DaySection({ day }: { day: CalendarDay }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className={day.isToday ? "font-semibold" : "font-medium"} aria-current={day.isToday ? "date" : undefined}>
        {day.heading}
      </h2>
      {day.visits.length === 0 ? (
        <p>No appointments.</p>
      ) : (
        <ul>{day.visits.map((visit) => <AppointmentRow key={visit.id} {...visit} />)}</ul>
      )}
    </section>
  );
}
