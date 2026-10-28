import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { DashboardScreen } from "@/features/dashboard/dashboard-screen";
import type { DashboardData } from "@/features/dashboard/load-dashboard";
import type { CalendarVisit, CurrentUser } from "@/lib/api/client";

const user: CurrentUser = { id: "synthetic-user", full_name: "Synthetic User", email: "synthetic@x.test", roles: ["receptionist"], clinic: { id: "synthetic-clinic", name: "Synthetic Clinic" } };
const page = { items: [], total: 0, page: 1, page_size: 20 };
const blank: DashboardData = { mode: "coordination", today: "2026-10-26", timezone: "Asia/Kolkata", appointments: [], followUps: page, recalls: page, lab: page };
const visit: CalendarVisit = { id: "synthetic-visit", starts_at: "2026-10-26T09:30:00+05:30", ends_at: "2026-10-26T10:00:00+05:30", status: "completed", patient: { id: "synthetic-patient", full_name: "Synthetic Patient", display_id: "P-0001" }, clinician: { id: "synthetic-clinician", full_name: "Synthetic Clinician" }, appointment_type: { id: "synthetic-type", name: "Scaling" } };

test("empty dashboard has honest zero totals, clinic date and existing shortcuts", () => {
  render(<DashboardScreen user={user} data={blank} />);
  expect(screen.getByText("Monday, 26 October")).toBeInTheDocument();
  expect(screen.getByText("No appointments today")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Appointments today: 0" })).toHaveAttribute("href", "/calendar?date=2026-10-26");
  expect(screen.getByRole("link", { name: "Register patient" })).toHaveAttribute("href", "/patients/new");
  expect(screen.getByRole("link", { name: "Find patient" })).toHaveAttribute("href", "/patients");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "No appointments today");
});

test("shows total counts, sorted six-visit preview, clinic wall time and patient links", () => {
  const visits = Array.from({ length: 8 }, (_, i) => ({ ...visit, id: `visit-${i}`, starts_at: `2026-10-26T${String(16-i).padStart(2, "0")}:30:00+05:30` }));
  render(<DashboardScreen user={user} data={{ ...blank, appointments: visits, followUps: { ...page, total: 42 }, recalls: { ...page, total: 31 }, lab: { ...page, total: 27 } }} />);
  expect(screen.getByRole("link", { name: "Appointments today: 8" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Follow-ups due: 42" })).toHaveAttribute("href", "/follow-ups");
  expect(screen.getByRole("link", { name: "Recalls due: 31" })).toHaveAttribute("href", "/recalls");
  expect(screen.getByRole("link", { name: "Open lab work: 27" })).toHaveAttribute("href", "/lab");
  const agenda = screen.getByRole("region", { name: "Today's appointments" });
  expect(within(agenda).getAllByRole("listitem")).toHaveLength(6);
  expect(within(agenda).getAllByRole("listitem")[0]).toHaveTextContent("09:30");
  expect(within(agenda).getAllByRole("link", { name: "Synthetic Patient" })[0]).toHaveAttribute("href", "/patients/synthetic-patient");
  expect(screen.getByText("Showing 6 of 8 appointments")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "8");
});

test("unavailable data is not shown as zero, caught-up, or a fabricated date", () => {
  render(<DashboardScreen user={user} data={{ ...blank, today: null, timezone: null, appointments: null, followUps: null, recalls: null, lab: null }} />);
  expect(screen.getByRole("link", { name: "Follow-ups due: unavailable" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Appointments today: unavailable" })).toHaveAttribute("href", "/calendar");
  expect(screen.getByText("Clinic date unavailable")).toBeInTheDocument();
  expect(screen.queryByText("You’re all caught up")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Unavailable");
});

test("follow-up preview links patients and distinguishes overdue from contacted", () => {
  const items = [{ id: "synthetic-followup", status: "contacted" as const, due_on: "2026-10-24", timing: "overdue" as const, patient: { id: "synthetic-patient", display_id: "P-0001", full_name: "Synthetic Patient", phone: "0000000000" } }];
  render(<DashboardScreen user={user} data={{ ...blank, followUps: { ...page, items, total: 1 } }} />);
  expect(screen.getByText("Overdue")).toBeInTheDocument();
  expect(screen.getByText("Contacted · ready to book")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Synthetic Patient" })).toHaveAttribute("href", "/patients/synthetic-patient");
});

test("inventory-only overview offers stock and rule destinations without patient shortcuts", () => {
  render(<DashboardScreen user={{ ...user, roles: ["inventory_admin"] }} data={{ ...blank, mode: "inventory" }} />);
  expect(screen.getByRole("link", { name: /Clinic inventory/ })).toHaveAttribute("href", "/inventory");
  expect(screen.getByRole("link", { name: /Visit type rules/ })).toHaveAttribute("href", "/inventory/rules");
  expect(screen.queryByRole("link", { name: "Register patient" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Today's appointments" })).not.toBeInTheDocument();
});

test("puts today's appointments and attention before summary metrics", () => {
  render(<DashboardScreen user={user} data={blank} />);
  const agenda = screen.getByRole("region", { name: "Today's appointments" });
  const attention = screen.getByRole("region", { name: "Attention queue" });
  const metric = screen.getByRole("link", { name: "Appointments today: 0" });
  expect(agenda.compareDocumentPosition(metric) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(attention.compareDocumentPosition(metric) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open today’s calendar" })).toHaveAttribute("href", "/calendar?date=2026-10-26");
  expect(screen.queryByText("A clear view.")).not.toBeInTheDocument();
});
