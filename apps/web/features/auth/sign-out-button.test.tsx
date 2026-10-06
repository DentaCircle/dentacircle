import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { SignOutButton } from "@/features/auth/sign-out-button";

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

test("posts logout and goes to the login page", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<SignOutButton />);

  await user.click(screen.getByRole("button", { name: "Sign out" }));

  expect(fetchMock).toHaveBeenCalledWith("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  });
  expect(push).toHaveBeenCalledWith("/login");
  expect(refresh).toHaveBeenCalledOnce();
});
