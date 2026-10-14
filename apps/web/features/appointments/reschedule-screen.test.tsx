import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ReschedulePage } from "@/features/appointments/reschedule-page";
import { RescheduleScreen } from "@/features/appointments/reschedule-screen";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const clinicians = [
  { id: "clinician-1", label: "Sample Clinician" },
  { id: "clinician-2", label: "Second Clinician" },
];

const slot = {
  starts_at: "2026-10-16T09:15:00+05:30",
  ends_at: "2026-10-16T09:45:00+05:30",
};

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("shows who and when, and loads times for the current clinician", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ is_open: true, slots: [slot] }));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <ReschedulePage
      status="ready"
      appointmentId="visit-1"
      patientName="Sample Ada"
      typeName="Consultation"
      currentWhen="09:00–09:30"
      clinicians={clinicians}
      initialClinicianId="clinician-1"
      initialDate="2026-10-16"
      today="2026-10-14"
    />,
  );

  expect(screen.getByText("Sample Ada, Consultation, 09:00–09:30")).toBeInTheDocument();
  expect(screen.getByLabelText("Clinician")).toHaveValue("clinician-1");
  expect(screen.getByLabelText("Date")).toHaveValue("2026-10-16");
  expect(await screen.findByRole("button", { name: "09:15" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/appointments/availability?date=2026-10-16&clinician_id=clinician-1&reschedule_appointment_id=visit-1",
    expect.objectContaining({ credentials: "same-origin" }),
  );
});

test("a closed day and a day with no times use the empty copy", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ is_open: false, slots: [] }));
  vi.stubGlobal("fetch", fetchMock);
  const closed = render(<ReadyScreen />);
  expect(await screen.findByText("The clinic is closed on this day.")).toBeInTheDocument();
  closed.unmount();

  fetchMock.mockImplementation(() => jsonResponse({ is_open: true, slots: [] }));
  render(<ReadyScreen />);
  expect(await screen.findByText("No free times on this day.")).toBeInTheDocument();
});

test("a visit that cannot move has no form", () => {
  const { rerender } = render(<ReschedulePage status="not-scheduled" />);
  expect(screen.getByRole("alert")).toHaveTextContent("This appointment can no longer be moved.");
  expect(screen.queryByRole("button", { name: "Reschedule" })).not.toBeInTheDocument();

  rerender(<ReschedulePage status="not-found" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Appointment not found");

  rerender(<ReschedulePage status="forbidden" />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<ReschedulePage status="error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
});

test("a double click reschedules once and opens the new day", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      return new Promise((resolve) => {
        resolveFetch = resolve;
      });
    }
    return jsonResponse({ is_open: true, slots: [slot] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<ReadyScreen />);
  await user.click(await screen.findByRole("button", { name: "09:15" }));

  const button = screen.getByRole("button", { name: "Reschedule" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(postCount(fetchMock)).toBe(1));
  resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);

  expect(postCount(fetchMock)).toBe(1);
  expect(push).toHaveBeenCalledWith("/calendar?view=day&date=2026-10-16&notice=rescheduled");
  expect(refresh).toHaveBeenCalled();
});

test("a taken time asks for another and reloads the times", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") return jsonResponse({}, 409);
    return jsonResponse({ is_open: true, slots: [slot] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<ReadyScreen />);
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Reschedule" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("That time is not available. Pick another.");
  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(2));
});

function ReadyScreen() {
  return (
    <RescheduleScreen
      appointmentId="visit-1"
      clinicians={clinicians}
      initialClinicianId="clinician-1"
      initialDate="2026-10-16"
      today="2026-10-14"
    />
  );
}

function jsonResponse(
  body: unknown,
  status = 200,
): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function postCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) => call[1]?.method === "POST").length;
}

function availabilityCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes("availability")).length;
}
