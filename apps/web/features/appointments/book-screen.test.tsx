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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
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

test("a late availability body cannot replace the newest clinician's slots", async () => {
  const user = userEvent.setup();
  let resolveFirstBody: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    if (String(input).includes("clinician_id=clinician-2")) {
      return jsonResponse({
        is_open: true,
        slots: [{ starts_at: "2026-10-12T10:00:00+05:30", ends_at: "2026-10-12T10:30:00+05:30" }],
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => new Promise((resolve) => {
        resolveFirstBody = resolve;
      }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(1));
  await user.selectOptions(screen.getByLabelText("Clinician"), "clinician-2");
  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(2));
  expect(await screen.findByRole("button", { name: "10:00" })).toBeInTheDocument();

  resolveFirstBody({ is_open: true, slots: [slot] });

  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByRole("button", { name: "09:15" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "10:00" })).toBeInTheDocument();
});

test("a late availability failure cannot replace the newest clinician's slots", async () => {
  const user = userEvent.setup();
  let rejectFirstBody: (reason?: unknown) => void = () => undefined;
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    if (String(input).includes("clinician_id=clinician-2")) {
      return jsonResponse({
        is_open: true,
        slots: [{ starts_at: "2026-10-12T10:00:00+05:30", ends_at: "2026-10-12T10:30:00+05:30" }],
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => new Promise((_resolve, reject) => {
        rejectFirstBody = reject;
      }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(1));
  await user.selectOptions(screen.getByLabelText("Clinician"), "clinician-2");
  expect(await screen.findByRole("button", { name: "10:00" })).toBeInTheDocument();

  rejectFirstBody(new Error("late body failure"));

  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "10:00" })).toBeInTheDocument();
});

test("an availability timeout shows fixed copy and a changed choice recovers", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    if (String(input).includes("clinician_id=clinician-2")) return availabilityResponse(String(input));
    return Promise.reject(new DOMException("timed out", "TimeoutError"));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
  await user.selectOptions(screen.getByLabelText("Clinician"), "clinician-2");
  expect(await screen.findByRole("button", { name: "10:00" })).toBeInTheDocument();
});

test("changing the date clears a selected slot until its replacement loads", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL) => availabilityResponse(String(input)));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  await user.click(await screen.findByRole("button", { name: "09:15" }));
  expect(screen.getByRole("button", { name: "Book appointment" })).toBeEnabled();
  await user.clear(screen.getByLabelText("Date"));
  await user.type(screen.getByLabelText("Date"), "2026-10-13");

  expect(screen.getByRole("button", { name: "Book appointment" })).toBeDisabled();
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("date=2026-10-13"),
      expect.anything(),
    ),
  );
});

test("unmounting cancels an in-flight availability request", async () => {
  let cancellation: AbortSignal | undefined;
  const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
    cancellation = init?.signal ?? undefined;
    return new Promise(() => undefined);
  });
  vi.stubGlobal("fetch", fetchMock);
  const rendered = render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  await waitFor(() => expect(cancellation).toBeDefined());
  rendered.unmount();

  expect(cancellation?.aborted).toBe(true);
});

test("a closed day and a day with no times use the empty copy", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ is_open: false, slots: [] }));
  vi.stubGlobal("fetch", fetchMock);
  const closed = render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));

  const book = screen.getByRole("button", { name: "Book appointment" });
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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/follow-ups/follow-1/book"
      doneUrl="/follow-ups?view=all&page=1&notice=booked"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book appointment" }));

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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/follow-ups/follow-1/book"
      doneUrl="/follow-ups?view=all&page=1&notice=booked"
      closedMessage="This follow-up is no longer open."
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book appointment" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This follow-up is no longer open.");
  expect(screen.queryByRole("button", { name: "Book appointment" })).not.toBeInTheDocument();
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
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book appointment" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("That time was just taken. Pick another.");
  await waitFor(() => expect(availabilityCount(fetchMock)).toBe(2));
});

test("a patient conflict identifies the patient conflict and reloads the list", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      return jsonResponse(
        { error: { code: "patient_busy", message: "ignored", request_id: "request-1" } },
        409,
      );
    }
    return availabilityResponse(String(input));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1?booked=1"
    />,
  );

  await user.click(await screen.findByRole("button", { name: "09:15" }));
  await user.click(screen.getByRole("button", { name: "Book appointment" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "That patient already has an appointment then. Pick another time.",
  );
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

test("shows the patient and updates the booking summary as choices change", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => availabilityResponse(String(input))));
  render(
    <BookScreen
      patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      patientId="patient-1"
      types={types}
      clinicians={clinicians}
      today="2026-10-12"
      submitUrl="/api/appointments"
      doneUrl="/patients/patient-1"
    />,
  );
  expect(screen.getByText(/Sample Patient/)).toHaveTextContent("P-0001");
  expect(screen.getByRole("region", { name: "Appointment summary" })).toHaveTextContent("Consultation · Sample Clinician");
  await user.click(await screen.findByRole("button", { name: "09:15" }));
  expect(screen.getByRole("region", { name: "Appointment summary" })).toHaveTextContent("09:15–09:45");
  await user.selectOptions(screen.getByLabelText("Clinician"), "clinician-2");
  expect(screen.getByRole("region", { name: "Appointment summary" })).toHaveTextContent("Second Clinician");
  expect(screen.getByRole("region", { name: "Appointment summary" })).toHaveTextContent("Choose a time");
});

test("groups available slots by clinic wall time and explains empty availability", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ is_open: true, slots: [slot, {
    starts_at: "2026-10-12T14:00:00+05:30", ends_at: "2026-10-12T14:30:00+05:30",
  }] }));
  vi.stubGlobal("fetch", fetchMock);
  const rendered = render(
    <BookScreen patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
      types={types} clinicians={clinicians} today="2026-10-12"
      submitUrl="/api/appointments" doneUrl="/patients" />,
  );
  expect(await screen.findByRole("group", { name: "Morning free times" })).toHaveTextContent("09:15");
  expect(screen.getByRole("group", { name: "Afternoon free times" })).toHaveTextContent("14:00");
  rendered.unmount();
  fetchMock.mockImplementation(() => jsonResponse({ is_open: true, slots: [] }));
  render(<BookScreen patient={{ full_name: "Sample Patient", display_id: "P-0001" }}
    types={types} clinicians={clinicians} today="2026-10-12"
    submitUrl="/api/appointments" doneUrl="/patients" />);
  expect(await screen.findByText("Try another date, clinician or appointment type.")).toBeInTheDocument();
});
