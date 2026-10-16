import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CareSessionScreen } from "@/features/care-session/care-session-screen";
import type { CareSession } from "@/lib/api/client";

const VISIT = {
  patientId: "patient-1",
  patientName: "Sample Ada",
  timeRange: "10:00–10:30",
  status: "arrived",
};

const SESSION: CareSession = {
  id: "session-1",
  appointment_id: "visit-1",
  patient_id: "patient-1",
  recorded_by_name: "Synthetic Person",
  created_at: "2026-10-17T10:05:00+05:30",
  items: [
    {
      care_item_id: "item-1",
      name: "Sample service",
      plan_title: "Sample plan",
      status: "completed",
    },
  ],
};

test("a saved session lists what was recorded", () => {
  render(
    <CareSessionScreen
      status="ready"
      appointmentId="visit-1"
      visit={VISIT}
      session={SESSION}
      openPlans={[]}
      canRecord={false}
      notice="saved"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Care session saved.");
  expect(screen.getByText("Sample Ada")).toBeInTheDocument();
  expect(screen.getByText("10:00–10:30")).toBeInTheDocument();
  expect(screen.getByText("Arrived")).toBeInTheDocument();
  expect(screen.getByText("Recorded by Synthetic Person")).toBeInTheDocument();
  expect(screen.getByText(/Sample plan: Sample service/)).toBeInTheDocument();
  expect(screen.getByText("Completed")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save care session" })).not.toBeInTheDocument();
});

test("a visit that cannot be recorded says none was saved", () => {
  render(
    <CareSessionScreen
      status="ready"
      appointmentId="visit-1"
      visit={{ ...VISIT, status: "scheduled" }}
      session={null}
      openPlans={[]}
      canRecord={false}
      notice={null}
    />,
  );
  expect(screen.getByText("No care session recorded.")).toBeInTheDocument();
  expect(screen.getByText("Scheduled")).toBeInTheDocument();
});

test("a writer with nothing open is sent to the care page", () => {
  render(
    <CareSessionScreen
      status="ready"
      appointmentId="visit-1"
      visit={VISIT}
      session={null}
      openPlans={[]}
      canRecord
      notice={null}
    />,
  );
  expect(screen.getByText(/No open care items/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Care" })).toHaveAttribute("href", "/patients/patient-1/care");
});

test("load failures use the fixed copy", () => {
  const missing = render(
    <CareSessionScreen
      status="not-found"
      appointmentId="visit-1"
      visit={null}
      session={null}
      openPlans={[]}
      canRecord={false}
      notice={null}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");
  missing.unmount();
  const denied = render(
    <CareSessionScreen
      status="forbidden"
      appointmentId="visit-1"
      visit={null}
      session={null}
      openPlans={[]}
      canRecord={false}
      notice={null}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  denied.unmount();
  render(
    <CareSessionScreen
      status="error"
      appointmentId="visit-1"
      visit={null}
      session={null}
      openPlans={[]}
      canRecord={false}
      notice={null}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Care session could not be loaded.");
});
