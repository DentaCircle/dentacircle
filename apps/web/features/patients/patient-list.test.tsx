import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { PatientList } from "@/features/patients/patient-list";

const row = {
  displayId: "P-0001",
  fullName: "Sample Ada",
  phone: "9000000001",
  dateOfBirth: "1990-04-05",
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
      canCreate
      createdDisplayId="P-0001"
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Saved P-0001.");
  expect(screen.getByRole("link", { name: "New patient" })).toHaveAttribute("href", "/patients/new");
  expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("ada");
  expect(screen.getByRole("table")).toHaveTextContent("Sample Ada");
  expect(screen.getByRole("table")).toHaveTextContent("P-0001");
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
      canCreate
      createdDisplayId={null}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("Patients could not be loaded.");
});
