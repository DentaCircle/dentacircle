import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { StatusButton, type StatusTarget } from "@/features/calendar/status-button";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const HREF = "/calendar?view=week&date=2026-10-14&clinician=clinician-1";

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("arrived and start send one request at once", async () => {
  const user = userEvent.setup();
  for (const target of ["arrived", "in_progress"] as const) {
    const fetchMock = pendingFetch();
    vi.stubGlobal("fetch", fetchMock.fn);
    const view = render(<StatusButton appointmentId="visit-1" returnHref={HREF} target={target} />);
    const button = screen.getByRole("button", { name: target === "arrived" ? "Arrived" : "Start" });
    const first = user.click(button);
    const second = user.click(button);
    await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
    fetchMock.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    await Promise.all([first, second]);
    expect(fetchMock.fn).toHaveBeenCalledWith(
      "/api/appointments/visit-1/status",
      expect.objectContaining({
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ status: target }),
      }),
    );
    expect(push).toHaveBeenCalledWith(`${HREF}&notice=${target === "arrived" ? "arrived" : "in_progress"}`);
    expect(refresh).toHaveBeenCalled();
    view.unmount();
    push.mockReset();
    refresh.mockReset();
  }
});

test("no-show and complete ask first, and keep sends nothing", async () => {
  const user = userEvent.setup();
  const cases: { target: StatusTarget; label: string; question: string; notice: string }[] = [
    { target: "no_show", label: "No-show", question: "Mark as no-show?", notice: "no_show" },
    { target: "completed", label: "Complete", question: "Mark as completed?", notice: "completed" },
  ];
  for (const item of cases) {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<StatusButton appointmentId="visit-1" returnHref={HREF} target={item.target} />);
    await user.click(screen.getByRole("button", { name: item.label }));
    expect(screen.getByText(item.question)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: item.label })).toBeInTheDocument();
    view.unmount();
  }
});

test("yes on a confirmed action sends one request", async () => {
  const user = userEvent.setup();
  const fetchMock = pendingFetch();
  vi.stubGlobal("fetch", fetchMock.fn);
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  const yes = screen.getByRole("button", { name: "Yes" });
  const first = user.click(yes);
  const second = user.click(yes);
  await waitFor(() => expect(fetchMock.fn).toHaveBeenCalledTimes(1));
  fetchMock.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock.fn).toHaveBeenCalledTimes(1);
  expect(push).toHaveBeenCalledWith(`${HREF}&notice=completed`);
  expect(refresh).toHaveBeenCalled();
});

test("a conflict reloads with the status-changed notice", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) })));
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="arrived" />);
  await user.click(screen.getByRole("button", { name: "Arrived" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith(`${HREF}&notice=changed`));
  expect(refresh).toHaveBeenCalled();
});

test("each failure uses the fixed sentence", async () => {
  const user = userEvent.setup();
  const cases = [
    { status: 403, body: {}, text: "You do not have access.", reloads: false },
    {
      status: 422,
      body: validationBody("body.status: not_today"),
      text: "Arrived can only be set on the day of the visit.",
      reloads: false,
    },
    {
      status: 422,
      body: validationBody("body.status: not_started"),
      text: "No-show can only be set after the start time.",
      reloads: false,
    },
    { status: 500, body: {}, text: "Something went wrong.", reloads: false },
  ];
  for (const item of cases) {
    refresh.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: item.status, json: () => Promise.resolve(item.body) })),
    );
    const view = render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="arrived" />);
    await user.click(screen.getByRole("button", { name: "Arrived" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(item.text);
    if (item.reloads) expect(refresh).toHaveBeenCalled();
    else expect(refresh).not.toHaveBeenCalled();
    view.unmount();
  }
});

test("a timeout or a dropped request uses the same sentence", async () => {
  const user = userEvent.setup();
  const failures = [new DOMException("timed out", "TimeoutError"), new TypeError("failed")];
  for (const failure of failures) {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(failure)));
    const view = render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="arrived" />);
    await user.click(screen.getByRole("button", { name: "Arrived" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
    expect(screen.getByRole("button", { name: "Arrived" })).toBeEnabled();
    view.unmount();
  }
});

test("complete can send a follow-up date, and an empty date sends none", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  expect(screen.getByLabelText("Follow-up date")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Yes" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/appointments/visit-1/status",
    expect.objectContaining({ body: JSON.stringify({ status: "completed" }) }),
  );
  view.unmount();

  fetchMock.mockClear();
  push.mockReset();
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  await user.type(screen.getByLabelText("Follow-up date"), "2026-10-24");
  await user.click(screen.getByRole("button", { name: "Yes" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/appointments/visit-1/status",
      expect.objectContaining({
        body: JSON.stringify({ status: "completed", follow_up_due_on: "2026-10-24" }),
      }),
    ),
  );
});

test("a bad follow-up date stays in the confirm box", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 422,
        json: () => Promise.resolve(validationBody("body.follow_up_due_on: before_today")),
      }),
    ),
  );
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  await user.click(screen.getByRole("button", { name: "Yes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Choose a date from today through the next year.",
  );
  expect(screen.getByText("Mark as completed?")).toBeInTheDocument();
  expect(push).not.toHaveBeenCalled();
});

test("keep drops a follow-up date error before complete is opened again", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 422,
        json: () => Promise.resolve(validationBody("body.follow_up_due_on: before_today")),
      }),
    ),
  );
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="completed" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  await user.click(screen.getByRole("button", { name: "Yes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Choose a date from today through the next year.",
  );
  await user.click(screen.getByRole("button", { name: "Keep" }));
  await user.click(screen.getByRole("button", { name: "Complete" }));
  expect(screen.getByText("Mark as completed?")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("no-show does not ask for a follow-up date", async () => {
  const user = userEvent.setup();
  render(<StatusButton appointmentId="visit-1" returnHref={HREF} target="no_show" />);
  await user.click(screen.getByRole("button", { name: "No-show" }));
  expect(screen.getByText("Mark as no-show?")).toBeInTheDocument();
  expect(screen.queryByLabelText("Follow-up date")).not.toBeInTheDocument();
});

function validationBody(message: string): { error: { code: string; message: string; request_id: string } } {
  return { error: { code: "validation_error", message, request_id: "req-1" } };
}

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
