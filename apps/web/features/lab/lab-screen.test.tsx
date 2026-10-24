import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { AddLabForm } from "@/features/lab/add-form";
import { ClinicLabScreen } from "@/features/lab/clinic-screen";
import { PatientLabScreen } from "@/features/lab/patient-screen";
import type { LabRow } from "@/features/lab/rows";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const pending: LabRow = {
  id: "lab-1",
  title: "Crown",
  status: "pending",
  statusLabel: "Pending",
  expectedOn: "12 Oct 2026",
  overdue: true,
  visit: "Visit: Consultation, 2026-10-12 10:00",
  addedBy: "Sample Desk, 2026-10-12 10:05",
  documentsHref: "/patients/p-1/documents?lab_work_id=lab-1",
  patient: { id: "p-1", displayId: "P-0001", fullName: "Sample Ada" },
};

test("a pending row can be marked ready or cancelled, and a final row has no buttons", () => {
  render(
    <PatientLabScreen
      status="ready"
      patientId="p-1"
      rows={[pending, { ...pending, id: "lab-2", status: "collected", statusLabel: "Collected" }]}
      page={1}
      pageSize={20}
      total={2}
      isPatientInactive={false}
      notice="ready"
    />,
  );
  expect(
    screen.getByText("Marked ready. Active patients are added to the Follow-ups queue."),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark ready" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Mark collected" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Documents" })[0]).toHaveAttribute(
    "href",
    "/patients/p-1/documents?lab_work_id=lab-1",
  );
});

test("the clinic open list shows Overdue only on an overdue row", () => {
  render(
    <ClinicLabScreen
      status="ready"
      rows={[pending, { ...pending, id: "lab-2", status: "ready", statusLabel: "Ready", overdue: false }]}
      total={2}
      page={1}
      pageSize={20}
      view="open"
      notice={null}
    />,
  );
  expect(screen.getAllByText("Overdue")).toHaveLength(1);
  expect(screen.getAllByRole("link", { name: "Sample Ada" })[0]).toHaveAttribute(
    "href",
    "/patients/p-1/lab?page=1",
  );
});

test("an empty open list says no lab work is open", () => {
  render(
    <ClinicLabScreen
      status="empty"
      rows={[]}
      total={0}
      page={1}
      pageSize={20}
      view="open"
      notice={null}
    />,
  );
  expect(screen.getByText("No lab work is open.")).toBeInTheDocument();
});

test("an empty title is refused before the request", async () => {
  render(<AddLabForm patientId="p-1" />);
  await userEvent.click(screen.getByRole("button", { name: "Add lab work" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a title.");
});

test("an inactive patient has no add form", () => {
  render(
    <PatientLabScreen
      status="empty"
      patientId="p-1"
      rows={[]}
      page={1}
      pageSize={20}
      total={0}
      isPatientInactive
      notice={null}
    />,
  );
  expect(screen.queryByRole("button", { name: "Add lab work" })).not.toBeInTheDocument();
  expect(screen.getByText("This patient is inactive, so lab work cannot be added.")).toBeInTheDocument();
});
