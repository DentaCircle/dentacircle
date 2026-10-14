import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CalendarScreen } from "@/features/calendar/calendar-screen";
import type { CalendarDay } from "@/features/calendar/day-section";

const clinicians = [{ id: "clinician-1", label: "Sample Clinician" }];

const scheduled: CalendarDay["visits"][number] = {
  id: "visit-1",
  timeRange: "09:15–09:45",
  patientId: "patient-1",
  patientName: "Sample Ada",
  displayId: "P-0001",
  typeName: "Consultation",
  clinicianName: "Sample Clinician",
  status: "scheduled",
};

test("a day lists the visit and hides a scheduled badge", () => {
  render(
    <CalendarScreen
      status="ready"
      view="day"
      date="2026-10-14"
      today="2026-10-14"
      clinician={null}
      clinicians={clinicians}
      notice={null}
      days={[day("2026-10-14", "Wed 14 Oct", true, [scheduled])]}
    />,
  );

  expect(screen.getByText("09:15–09:45")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sample Ada" })).toHaveAttribute("href", "/patients/patient-1");
  expect(screen.getByText("P-0001")).toBeInTheDocument();
  expect(screen.getByRole("listitem")).toHaveTextContent("Consultation");
  expect(screen.getByRole("listitem")).toHaveTextContent("Sample Clinician");
  expect(screen.queryByText("Scheduled")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Wed 14 Oct" })).toHaveAttribute("aria-current", "date");
});

test("a status other than scheduled shows a badge", () => {
  render(
    <CalendarScreen
      status="ready"
      view="day"
      date="2026-10-14"
      today="2026-10-13"
      clinician={null}
      clinicians={clinicians}
      notice={null}
      days={[day("2026-10-14", "Wed 14 Oct", false, [{ ...scheduled, status: "no_show" }])]}
    />,
  );

  expect(screen.getByText("No-show")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Wed 14 Oct" })).not.toHaveAttribute("aria-current");
});

test("an empty day says there are no appointments", () => {
  render(
    <CalendarScreen
      status="ready"
      view="day"
      date="2026-10-14"
      today="2026-10-14"
      clinician={null}
      clinicians={clinicians}
      notice={null}
      days={[day("2026-10-14", "Wed 14 Oct", true, [])]}
    />,
  );

  expect(screen.getByText("No appointments.")).toBeInTheDocument();
});

test("a week shows every day and marks today", () => {
  const days = ["Mon 12 Oct", "Tue 13 Oct", "Wed 14 Oct", "Thu 15 Oct", "Fri 16 Oct", "Sat 17 Oct", "Sun 18 Oct"].map(
    (heading, index) => day(`2026-10-${12 + index}`, heading, heading === "Wed 14 Oct", index === 2 ? [scheduled] : []),
  );
  render(
    <CalendarScreen
      status="ready"
      view="week"
      date="2026-10-14"
      today="2026-10-14"
      clinician="clinician-1"
      clinicians={clinicians}
      notice={null}
      days={days}
    />,
  );

  expect(screen.getByRole("heading", { name: "Mon 12 Oct" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Sun 18 Oct" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Wed 14 Oct" })).toHaveAttribute("aria-current", "date");
  expect(screen.getAllByText("No appointments.")).toHaveLength(6);
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
    "href",
    "/calendar?view=week&date=2026-10-07&clinician=clinician-1",
  );
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
    "href",
    "/calendar?view=week&date=2026-10-21&clinician=clinician-1",
  );
  expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute(
    "href",
    "/calendar?view=week&date=2026-10-14&clinician=clinician-1",
  );
  expect(screen.getByRole("link", { name: "Day" })).toHaveAttribute(
    "href",
    "/calendar?view=day&date=2026-10-14&clinician=clinician-1",
  );
  expect(screen.getByRole("link", { name: "Week" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("combobox", { name: "Clinician" })).toHaveValue("clinician-1");
  expect(screen.getByRole("option", { name: "All clinicians" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
});

test("a known notice is shown and an access or load failure replaces the list", () => {
  const { rerender } = render(
    <CalendarScreen
      status="ready"
      view="day"
      date="2026-10-14"
      today="2026-10-14"
      clinician={null}
      clinicians={clinicians}
      notice="cancelled"
      days={[]}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Appointment cancelled.");

  rerender(<CalendarScreen status="forbidden" />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByText("No appointments.")).not.toBeInTheDocument();

  rerender(<CalendarScreen status="error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
});

function day(date: string, heading: string, isToday: boolean, visits: CalendarDay["visits"]): CalendarDay {
  return { date, heading, isToday, visits };
}
