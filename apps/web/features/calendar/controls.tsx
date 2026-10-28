import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { calendarHref, stepDate, type CalendarViewMode } from "@/features/calendar/links";

export type ClinicianOption = {
  id: string;
  label: string;
};

export function CalendarControls({
  view,
  date,
  today,
  clinician,
  clinicians,
}: {
  view: CalendarViewMode;
  date: string;
  today: string;
  clinician: string | null;
  clinicians: ClinicianOption[];
}) {
  const shared = { view, clinician };
  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="Calendar days" className="flex flex-wrap items-center gap-3 text-sm">
        <Link href={calendarHref({ ...shared, date: stepDate(date, view, -1) })}>Previous</Link>
        <Link href={calendarHref({ ...shared, date: stepDate(date, view, 1) })}>Next</Link>
        <Link href={calendarHref({ ...shared, date: today })}>Today</Link>
        <Link
          href={calendarHref({ view: "day", date, clinician })}
          aria-current={view === "day" ? "page" : undefined}
        >
          Day
        </Link>
        <Link
          href={calendarHref({ view: "week", date, clinician })}
          aria-current={view === "week" ? "page" : undefined}
        >
          Week
        </Link>
      </nav>
      <form method="get" action="/calendar" className="flex flex-wrap items-end gap-3">
        <input type="hidden" name="view" value={view} />
        <div className="flex flex-col gap-2">
          <Label htmlFor="calendar-date">Date</Label>
          <Input key={date} id="calendar-date" name="date" type="date" defaultValue={date} required />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="clinician">Clinician</Label>
          <select
            id="clinician"
            name="clinician"
            defaultValue={clinician ?? ""}
            className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm"
          >
            <option value="">All clinicians</option>
            {clinicians.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit">Apply</Button>
      </form>
    </div>
  );
}
