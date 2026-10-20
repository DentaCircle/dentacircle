import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { BookScreen } from "@/features/appointments/book-screen";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const types = [{ id: "type-1", label: "Consultation" }];
const clinicians = [
  { id: "clinician-1", label: "Sample Clinician" },
  { id: "clinician-2", label: "Second Clinician" },
];

const slot = {
  starts_at: "2026-10-12T09:15:00+05:30",
  ends_at: "2026-10-12T09:45:00+05:30",
};

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("loads free times and shows them as clock buttons", async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => availabilityResponse(String(input)));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  expect(await screen.findByRole("button", { name: "09:15" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/appointments/availability?date=2026-10-12&clinician_id=clinician-1&appointment_type_id=type-1",
    expect.objectContaining({ credentials: "same-origin" }),
  );
});

test("changing the clinician loads that clinician's times", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL) => availabilityResponse(String(input)));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  await screen.findByRole("button", { name: "09:15" });

  await user.selectOptions(screen.getByLabelText("Clinician"), "clinician-2");

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("clinician_id=clinician-2"),
      expect.anything(),
    ),
  );
});

test("a closed day and a day with no times use the empty copy", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ is_open: false, slots: [] }));
  vi.stubGlobal("fetch", fetchMock);
  const closed = render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  expect(await screen.findByText("The clinic is closed on this day.")).toBeInTheDocument();
  closed.unmount();

  fetchMock.mockImplementation(() => jsonResponse({ is_open: true, slots: [] }));
  render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  expect(await screen.findByText("No free times on this day.")).toBeInTheDocument();
});

test("a double click books once", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      return new Promise((resolve) => {
        resolveFetch = resolve;
      });
    }
    return availabilityResponse(String(input));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));

  const book = screen.getByRole("button", { name: "Book" });
  const first = user.click(book);
  const second = user.click(book);
  await waitFor(() => expect(postCount(fetchMock)).toBe(1));
  resolveFetch({ ok: true, status: 201, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);

  expect(postCount(fetchMock)).toBe(1);
  expect(push).toHaveBeenCalledWith("/patients/patient-1?booked=1");
});

test("a follow-up booking posts to the given URL without a patient id", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") return jsonResponse({}, 201);
    return availabilityResponse(String(input));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/follow-ups/follow-1/book"
      doneUrl="/follow-ups?view=all&page=1&notice=booked"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book" }));

  await waitFor(() => expect(postCount(fetchMock)).toBe(1));
  const posted = fetchMock.mock.calls.find((call) => call[1]?.method === "POST");
  expect(posted?.[0]).toBe("/api/follow-ups/follow-1/book");
  expect(JSON.parse(String(posted?.[1]?.body))).toEqual({
    clinician_id: "clinician-1",
    appointment_type_id: "type-1",
    starts_at: "2026-10-12T09:15:00+05:30",
  });
  expect(push).toHaveBeenCalledWith("/follow-ups?view=all&page=1&notice=booked");
});

test("an already booked follow-up is replaced with a plain message", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      return jsonResponse({ error: { code: "invalid_status", message: "changed", request_id: "r1" } }, 409);
    }
    return availabilityResponse(String(input));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/follow-ups/follow-1/book"
      doneUrl="/follow-ups?view=all&page=1&notice=booked"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This follow-up is no longer open.");
  expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();
});

test("a taken time asks for another and reloads the list", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") return jsonResponse({}, 409);
    return availabilityResponse(String(input));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("That time was just taken. Pick another.");
  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(2));
});

function availabilityResponse(url: string): ReturnType<typeof jsonResponse> {
  if (url.includes("clinician_id=clinician-2")) {
    return jsonResponse({
      is_open: true,
      slots: [{ starts_at: "2026-10-12T10:00:00+05:30", ends_at: "2026-10-12T10:30:00+05:30" }],
    });
  }
  return jsonResponse({ is_open: true, slots: [slot] });
}

function jsonResponse(body: unknown, status = 200): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }> {
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
