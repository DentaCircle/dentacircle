import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { PatientDetail, registeredOn } from "@/features/patients/patient-detail";

const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const patient = {
  id: "00000000-0000-4000-8000-000000000010",
  displayId: "P-0001",
  fullName: "Sample Ada",
  phone: "9000000001",
  dateOfBirth: "1990-04-05",
  status: "active" as const,
  registeredOn: "2026-10-08",
};

afterEach(() => {
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("shows the patient, an edit link and a status button", () => {
  render(
    <PatientDetail
      status="ready"
      patient={patient}
      canEdit
      canBook
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );

  expect(screen.getByRole("heading", { name: "Sample Ada" })).toBeInTheDocument();
  expect(screen.getByText("P-0001")).toBeInTheDocument();
  expect(screen.getByText("9000000001")).toBeInTheDocument();
  expect(screen.getByText("1990-04-05")).toBeInTheDocument();
  expect(screen.getByText("Active")).toBeInTheDocument();
  expect(screen.getByText("2026-10-08")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Care" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/care",
  );
  expect(screen.getByRole("link", { name: "Lab" })).toHaveAttribute(
    "href",
    `/patients/${patient.id}/lab`,
  );
  expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/documents",
  );
  expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/timeline",
  );
  expect(screen.getByRole("link", { name: "Book appointment" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/book",
  );
  expect(screen.getByText("No upcoming appointments.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/edit",
  );
  expect(screen.getByRole("button", { name: "Mark inactive" })).toBeInTheDocument();
});

test("registeredOn keeps the date prefix", () => {
  expect(registeredOn("2026-10-08T18:30:00+00:00")).toBe("2026-10-08");
});

test("hides edit and the status button when the role cannot edit", () => {
  render(
    <PatientDetail
      status="ready"
      patient={patient}
      canEdit={false}
      canBook={false}
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );

  expect(screen.getByText("Active")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Care" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute(
    "href",
    "/patients/00000000-0000-4000-8000-000000000010/timeline",
  );
  expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Book appointment" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Mark inactive" })).not.toBeInTheDocument();
});

test("shows not found, forbidden and error states", () => {
  const { rerender } = render(
    <PatientDetail
      status="not-found"
      patient={null}
      canEdit={false}
      canBook={false}
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Patient not found");

  rerender(
    <PatientDetail
      status="forbidden"
      patient={null}
      canEdit={false}
      canBook={false}
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(
    <PatientDetail
      status="error"
      patient={null}
      canEdit={false}
      canBook={false}
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The patient could not be loaded.");
  expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Timeline" })).not.toBeInTheDocument();
});

test("shows saved after an edit", () => {
  render(
    <PatientDetail
      status="ready"
      patient={patient}
      canEdit
      canBook={false}
      saved
      booked={false}
      upcomingItems={[]}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Saved.");
});

test("a status click updates the page and a double click sends one request", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <PatientDetail
      status="ready"
      patient={patient}
      canEdit
      canBook
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );

  const button = screen.getByRole("button", { name: "Mark inactive" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(fetchMock).toHaveBeenCalledWith("/api/patients/00000000-0000-4000-8000-000000000010/status", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ status: "inactive" }),
  });
  resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Inactive")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark active" })).toBeInTheDocument();
  expect(refresh).toHaveBeenCalledOnce();
});

test("shows upcoming visits and Booked", () => {
  render(
    <PatientDetail
      status="ready"
      patient={patient}
      canEdit
      canBook
      saved={false}
      booked
      upcomingItems={[
        {
          id: "visit-1",
          date: "2026-10-12",
          time: "09:15",
          typeName: "Consultation",
          clinicianName: "Sample Clinician",
        },
      ]}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Booked.");
  expect(screen.getByRole("heading", { name: "Upcoming appointments" })).toBeInTheDocument();
  expect(screen.getByText("2026-10-12 09:15 Consultation Sample Clinician")).toBeInTheDocument();
});

test("hides the book link when the patient is inactive", () => {
  render(
    <PatientDetail
      status="ready"
      patient={{ ...patient, status: "inactive" }}
      canEdit
      canBook
      saved={false}
      booked={false}
      upcomingItems={[]}
    />,
  );

  expect(screen.queryByRole("link", { name: "Book appointment" })).not.toBeInTheDocument();
});
