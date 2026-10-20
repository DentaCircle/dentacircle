import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ContactedButton } from "@/features/recalls/contacted-button";

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

test("a successful mark reloads the queue", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200 }),
  );
  render(<ContactedButton recallId="rc-1" view="due" page={1} />);

  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/recalls?page=1&notice=contacted");
  });
});

test("a conflict reloads with the changed notice", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409 }));
  render(<ContactedButton recallId="rc-1" view="all" page={2} />);

  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/recalls?view=all&page=2&notice=changed");
  });
});
