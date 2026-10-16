import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { SessionForm } from "@/features/care-session/session-form";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const PLANS = [
  {
    id: "plan-1",
    title: "Sample plan",
    items: [{ id: "item-1", name: "Scaling", status: "planned" as const }],
  },
  {
    id: "plan-2",
    title: "Second plan",
    items: [{ id: "item-2", name: "Root canal", status: "started" as const }],
  },
];

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("save stays disabled until an item is chosen, and a started item has no Started choice", () => {
  render(<SessionForm appointmentId="visit-1" plans={PLANS} />);
  expect(screen.getByText("Choose what was done today. No clinical notes.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save care session" })).toBeDisabled();
  const started = screen.getByRole("group", { name: "Root canal" });
  expect(within(started).queryByRole("radio", { name: "Started" })).not.toBeInTheDocument();
  expect(within(started).getByRole("radio", { name: "Completed" })).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

test("keep sends nothing, and yes sends one request", async () => {
  const user = userEvent.setup();
  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  render(<SessionForm appointmentId="visit-1" plans={PLANS} />);
  const scaling = screen.getByRole("group", { name: "Scaling" });
  await user.click(within(scaling).getByRole("radio", { name: "Completed" }));
  await user.click(screen.getByRole("button", { name: "Save care session" }));
  expect(screen.getByText("Save care session? Completed items cannot be undone.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep" }));
  expect(fetchMock.fn).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Save care session" }));
  const yes = screen.getByRole("button", { name: "Yes" });
  const first = user.click(yes);
  const second = user.click(yes);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock.fn).toHaveBeenCalledWith(
    "/api/appointments/visit-1/care-session",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ items: [{ care_item_id: "item-1", status: "completed" }] }),
    }),
  );
  expect(push).toHaveBeenCalledWith("/appointments/visit-1/care?notice=saved");
  expect(refresh).toHaveBeenCalled();
});

test("each failure shows the matching notice", async () => {
  const user = userEvent.setup();
  const cases = [
    { code: "session_exists", status: 409, notice: "session_exists" },
    { code: "invalid_status", status: 409, notice: "invalid_status" },
    { code: "item_changed", status: 409, notice: "item_changed" },
  ];
  for (const item of cases) {
    push.mockReset();
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
    const view = render(<SessionForm appointmentId="visit-1" plans={PLANS} />);
    await user.click(within(screen.getByRole("group", { name: "Scaling" })).getByRole("radio", { name: "Started" }));
    await user.click(screen.getByRole("button", { name: "Save care session" }));
    await user.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(`/appointments/visit-1/care?notice=${item.notice}`),
    );
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save care session" })).toBeDisabled();
    view.unmount();
  }
});

test("a refused save stays on the form", async () => {
  const user = userEvent.setup();
  const cases = [
    { status: 422, code: "validation_error", text: "Something went wrong." },
    { status: 403, code: "forbidden", text: "You do not have access." },
  ];
  for (const item of cases) {
    push.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: item.status,
          json: () =>
            Promise.resolve({ error: { code: item.code, message: "unknown_item", request_id: "r" } }),
        }),
      ),
    );
    const view = render(<SessionForm appointmentId="visit-1" plans={PLANS} />);
    await user.click(
      within(screen.getByRole("group", { name: "Scaling" })).getByRole("radio", { name: "Started" }),
    );
    await user.click(screen.getByRole("button", { name: "Save care session" }));
    await user.click(screen.getByRole("button", { name: "Yes" }));
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
