import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CancelButton } from "@/features/calendar/cancel-button";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("keep closes the question without a request", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<CancelButton appointmentId="visit-1" returnHref="/calendar?view=day&date=2026-10-14" />);

  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByText("Cancel this appointment?")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep" }));

  expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a double click cancels once and reloads with the notice", async () => {
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
    <CancelButton
      appointmentId="visit-1"
      returnHref="/calendar?view=week&date=2026-10-14&clinician=clinician-1"
    />,
  );
  await user.click(screen.getByRole("button", { name: "Cancel" }));

  const yes = screen.getByRole("button", { name: "Yes, cancel" });
  const first = user.click(yes);
  const second = user.click(yes);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith("/api/appointments/visit-1/cancel", {
    method: "POST",
    credentials: "same-origin",
  });
  expect(push).toHaveBeenCalledWith(
    "/calendar?view=week&date=2026-10-14&clinician=clinician-1&notice=cancelled",
  );
  expect(refresh).toHaveBeenCalled();
});

test("a conflict explains that cancel is no longer possible and reloads", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 409 })));
  render(<CancelButton appointmentId="visit-1" returnHref="/calendar?view=day&date=2026-10-14" />);
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This appointment can no longer be cancelled.");
  expect(refresh).toHaveBeenCalled();
});

test("forbidden and other failures use the fixed sentences", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 403 }));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<CancelButton appointmentId="visit-1" returnHref="/calendar?view=day&date=2026-10-14" />);
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("You do not have access.");

  fetchMock.mockImplementation(() => Promise.resolve({ ok: false, status: 500 }));
  view.rerender(<CancelButton appointmentId="visit-1" returnHref="/calendar?view=day&date=2026-10-14" />);
  await user.click(screen.getByRole("button", { name: "Keep" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
});
