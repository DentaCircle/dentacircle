import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { canAdvanceAppointments } from "@/features/appointments/access";
import { AppointmentRow } from "@/features/calendar/appointment-row";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const STATUSES = ["scheduled", "arrived", "in_progress", "completed", "cancelled", "no_show"] as const;
const ROLES = ["receptionist", "clinician", "clinic_admin", "inventory_admin"] as const;

const ACTIONS: Record<(typeof STATUSES)[number], Record<"advance" | "desk", string[]>> = {
  scheduled: {
    advance: ["Reschedule", "Cancel", "Mark arrived", "Mark no-show"],
    desk: ["Reschedule", "Cancel", "Mark arrived", "Mark no-show"],
  },
  arrived: { advance: ["Start"], desk: [] },
  in_progress: { advance: ["Complete"], desk: [] },
  completed: { advance: [], desk: [] },
  cancelled: { advance: [], desk: [] },
  no_show: { advance: [], desk: [] },
};

test("each status shows the actions for that role", () => {
  for (const status of STATUSES) {
    for (const role of ROLES) {
      const canAdvance = canAdvanceAppointments([role]);
      const { unmount } = render(
        <AppointmentRow
          id="visit-1"
          timeRange="09:15–09:45"
          patientId="patient-1"
          patientName="Sample Ada"
          displayId="P-0001"
          typeName="Consultation"
          clinicianName="Sample Clinician"
          status={status}
          canAdvance={canAdvance}
          returnHref="/calendar?view=day&date=2026-10-14"
        />,
      );
      const expected = ACTIONS[status][canAdvance ? "advance" : "desk"];
      for (const name of ["Reschedule", "Cancel", "Mark arrived", "Mark no-show", "Start", "Complete"]) {
        const control =
          name === "Reschedule" ? screen.queryByRole("link", { name }) : screen.queryByRole("button", { name });
        if (expected.includes(name)) expect(control).toBeInTheDocument();
        else expect(control).not.toBeInTheDocument();
      }
      const care = screen.queryByRole("link", { name: "Care session" });
      const showsCare = status === "arrived" || status === "in_progress" || status === "completed";
      if (showsCare) expect(care).toHaveAttribute("href", "/appointments/visit-1/care");
      else expect(care).not.toBeInTheDocument();
      unmount();
    }
  }
});

test("keeps visit facts separate from labeled actions", () => {
  render(<AppointmentRow id="visit-1" timeRange="09:15–09:45" patientId="p-1"
    patientName="Sample Patient" displayId="P-0001" typeName="Consultation"
    clinicianName="Sample Clinician" status="scheduled" canAdvance returnHref="/calendar" />);
  const actions = screen.getByRole("group", { name: "Visit actions" });
  expect(actions).toHaveTextContent("Mark arrived");
  expect(actions).toHaveTextContent("Documents");
  expect(actions).not.toHaveTextContent("Sample Patient");
  expect(screen.getByText("Scheduled")).toBeInTheDocument();
});
