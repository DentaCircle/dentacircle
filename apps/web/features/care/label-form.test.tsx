import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CareScreen } from "@/features/care/care-screen";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const patientId = "patient-1";
const plan = {
  id: "plan-1",
  patient_id: patientId,
  title: "Sample plan",
  created_at: "2026-10-15T10:00:00+00:00",
  is_open: true,
  items: [
    { id: "item-1", name: "Cleaning", status: "planned" as const, created_at: "2026-10-15T10:01:00+00:00" },
  ],
};

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("a new plan sends one request and a blank title stays on the field", async () => {
  const user = userEvent.setup();
  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  const view = render(<CareScreen status="ready" patientId={patientId} plans={[]} canWrite notice={null} followUp={{ status: "ready", followUp: null }} />);
  await user.type(screen.getByLabelText("Title"), "Sample plan");
  const button = screen.getByRole("button", { name: "New care plan" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock.fn).toHaveBeenCalledWith(
    "/api/patients/patient-1/care-plans",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ title: "Sample plan" }) }),
  );
  expect(push).toHaveBeenCalledWith("/patients/patient-1/care?notice=plan_added");
  view.unmount();

  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            error: { code: "validation_error", message: "body.title: string_too_short", request_id: "r" },
          }),
      }),
    ),
  );
  render(<CareScreen status="ready" patientId={patientId} plans={[]} canWrite notice={null} followUp={{ status: "ready", followUp: null }} />);
  await user.click(screen.getByRole("button", { name: "New care plan" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter a title.");
});

test("adding an item reports inactive and a rename sends one request", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () =>
          Promise.resolve({ error: { code: "patient_inactive", message: "inactive", request_id: "r" } }),
      }),
    ),
  );
  const view = render(<CareScreen status="ready" patientId={patientId} plans={[plan]} canWrite notice={null} followUp={{ status: "ready", followUp: null }} />);
  await user.type(screen.getByLabelText("Service name"), "Polish");
  await user.click(screen.getByRole("button", { name: "Add item" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This patient is inactive.");
  expect(screen.getByText("Service name only. No clinical notes.")).toBeInTheDocument();
  view.unmount();

  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  render(<CareScreen status="ready" patientId={patientId} plans={[plan]} canWrite notice={null} followUp={{ status: "ready", followUp: null }} />);
  await user.click(screen.getByRole("button", { name: "Rename" }));
  await user.type(screen.getByLabelText("Name"), "Polish");
  const rename = screen.getByRole("button", { name: "Rename" });
  const first = user.click(rename);
  const second = user.click(rename);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock.fn).toHaveBeenCalledWith(
    "/api/care-items/item-1",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "Polish" }) }),
  );
  expect(push).toHaveBeenCalledWith("/patients/patient-1/care?notice=item_updated");
});

function pendingFetch(): { fn: ReturnType<typeof vi.fn>; resolve: (value: unknown) => void } {
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fn = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
  );
  return { fn, resolve: (value) => resolveFetch(value) };
}
