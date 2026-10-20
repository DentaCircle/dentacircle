import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ContactedButton } from "@/features/follow-ups/contacted-button";

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

test("mark contacted refreshes the row as contacted", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })));
  render(<ContactedButton followUpId="fu-1" view="due" page={1} />);
  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  expect(push).toHaveBeenCalledWith("/follow-ups?page=1&notice=contacted");
  expect(refresh).toHaveBeenCalled();
});

test("a 409 refreshes and shows that the follow-up has already changed", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) })));
  render(<ContactedButton followUpId="fu-1" view="all" page={2} />);
  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  expect(push).toHaveBeenCalledWith("/follow-ups?view=all&page=2&notice=changed");
});

test("a double click sends one request", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<ContactedButton followUpId="fu-1" view="due" page={1} />);
  const button = screen.getByRole("button", { name: "Mark contacted" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
