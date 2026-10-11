import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { PatientList } from "@/features/patients/patient-list";

const row = {
  id: "00000000-0000-4000-8000-000000000010",
  displayId: "P-0001",
  fullName: "Sample Ada",
  phone: "9000000001",
  dateOfBirth: "1990-04-05",
  status: "active" as const,
};

test("shows the list, search, a new-patient link and page links", () => {
  render(
    <PatientList
      status="ready"
      items={[row]}
      total={25}
      page={2}
      pageSize={10}
      query="ada"
      statusFilter="all"
      canCreate
      createdDisplayId="P-0001"
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Saved P-0001.");
  expect(screen.getByRole("link", { name: "New patient" })).toHaveAttribute("href", "/patients/new");
  expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("ada");
  expect(screen.getByRole("link", { name: "P-0001" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010",
  );
  expect(screen.getByRole("link", { name: "Sample Ada" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010",
  );
  expect(screen.getByRole("table")).toHaveTextContent("P-0001");
  expect(screen.getByRole("link", { name: "All" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Active" })).toHaveAttribute("href", "/patients?q=ada&status=active&page=1");
  expect(screen.getByRole("link", { name: "Inactive" })).toHaveAttribute(
    "href",
    "/patients?q=ada&status=inactive&page=1",
  );
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/patients?q=ada&page=1");
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "/patients?q=ada&page=3");
});

test("hides the new-patient link when the role cannot create", () => {
  render(
    <PatientList
      status="ready"
      items={[row]}
      total={1}
      page={1}
      pageSize={20}
      query=""
      statusFilter="all"
      canCreate={false}
      createdDisplayId={null}
    />,
  );

  expect(screen.queryByRole("link", { name: "New patient" })).not.toBeInTheDocument();
  expect(screen.getByText("Previous")).not.toHaveAttribute("href");
  expect(screen.getByText("Next")).not.toHaveAttribute("href");
});

test("shows an empty state", () => {
  render(
    <PatientList
      status="empty"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      query=""
      statusFilter="all"
      canCreate
      createdDisplayId={null}
    />,
  );

  expect(screen.getByText("No patients yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "New patient" })).toBeInTheDocument();
});

test("shows a no-match state", () => {
  render(
    <PatientList
      status="no-match"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      query="nobody"
      statusFilter="all"
      canCreate
      createdDisplayId={null}
    />,
  );

  expect(screen.getByText("No patients match")).toBeInTheDocument();
});

test("shows a forbidden state without the create link", () => {
  render(
    <PatientList
      status="forbidden"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      query=""
      statusFilter="all"
      canCreate={false}
      createdDisplayId={null}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByRole("link", { name: "New patient" })).not.toBeInTheDocument();
  expect(screen.queryByRole("searchbox", { name: "Search" })).not.toBeInTheDocument();
});

test("shows a generic error state", () => {
  render(
    <PatientList
      status="error"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      query=""
      statusFilter="all"
      canCreate
      createdDisplayId={null}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("Patients could not be loaded.");
});

test("links an inactive patient and keeps the status filter in the url", () => {
  render(
    <PatientList
      status="ready"
      items={[{ ...row, status: "inactive" }]}
      total={3}
      page={2}
      pageSize={1}
      query="ada"
      statusFilter="inactive"
      canCreate
      createdDisplayId={null}
    />,
  );

  const patientRow = screen.getByRole("row", { name: /Sample Ada/ });
  expect(patientRow).toHaveTextContent("Inactive");
  expect(screen.getByRole("link", { name: "Inactive" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "All" })).toHaveAttribute("href", "/patients?q=ada&page=1");
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
    "href",
    "/patients?q=ada&status=inactive&page=1",
  );
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
    "href",
    "/patients?q=ada&status=inactive&page=3",
  );
  expect(document.querySelector("input[name=status]")).toHaveValue("inactive");
});
