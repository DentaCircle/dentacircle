import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { StatusButton } from "@/features/care/status-button";
import type { CareStatusTarget } from "@/lib/api/client";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const PATIENT = "patient-1";

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("start sends one request at once", async () => {
  const user = userEvent.setup();
  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  render(<StatusButton patientId={PATIENT} itemId="item-1" target="started" />);
  const button = screen.getByRole("button", { name: "Start" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock.fn).toHaveBeenCalledWith(
    "/api/care-items/item-1/status",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ status: "started" }),
    }),
  );
  expect(push).toHaveBeenCalledWith("/patients/patient-1/care?notice=started");
  expect(refresh).toHaveBeenCalled();
});

test("complete and cancel ask first, and keep sends nothing", async () => {
  const user = userEvent.setup();
  const cases: { target: CareStatusTarget; label: string; question: string }[] = [
    { target: "completed", label: "Complete", question: "Mark as completed?" },
    { target: "cancelled", label: "Cancel", question: "Cancel this item?" },
  ];
  for (const item of cases) {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<StatusButton patientId={PATIENT} itemId="item-1" target={item.target} />);
    await user.click(screen.getByRole("button", { name: item.label }));
    expect(screen.getByText(item.question)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep" }));
    expect(fetchMock).not.toHaveBeenCalled();
    view.unmount();
  }
});

test("yes sends one request and a conflict reloads", async () => {
  const user = userEvent.setup();
  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  const view = render(<StatusButton patientId={PATIENT} itemId="item-1" target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  const yes = screen.getByRole("button", { name: "Yes" });
  const first = user.click(yes);
  const second = user.click(yes);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(push).toHaveBeenCalledWith("/patients/patient-1/care?notice=completed");
  view.unmount();

  push.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ error: { code: "invalid_status", message: "changed", request_id: "r" } }),
      }),
    ),
  );
  render(<StatusButton patientId={PATIENT} itemId="item-1" target="started" />);
  await user.click(screen.getByRole("button", { name: "Start" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/patients/patient-1/care?notice=changed"));
});

test("each failure uses the fixed sentence", async () => {
  const user = userEvent.setup();
  const cases = [
    { status: 403, code: "forbidden", text: "You do not have access." },
    { status: 422, code: "validation_error", text: "Something went wrong." },
    { status: 500, code: "internal_error", text: "Something went wrong." },
  ];
  for (const item of cases) {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: item.status,
          json: () => Promise.resolve({ error: { code: item.code, message: "x", request_id: "r" } }),
        }),
      ),
    );
    const view = render(<StatusButton patientId={PATIENT} itemId="item-1" target="started" />);
    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(item.text);
    expect(push).not.toHaveBeenCalled();
    view.unmount();
  }
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
