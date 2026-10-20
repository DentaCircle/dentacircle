import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ContactedButton } from "@/features/recalls/contacted-button";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());
const markRecallContacted = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/client", () => ({
  markRecallContacted,
}));

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  markRecallContacted.mockReset();
});

test("a successful mark reloads the queue", async () => {
  const user = userEvent.setup();
  markRecallContacted.mockResolvedValue({ ok: true, data: null });
  render(<ContactedButton recallId="rc-1" view="due" page={1} />);

  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/recalls?page=1&notice=contacted");
  });
});

test("a conflict reloads with the changed notice", async () => {
  const user = userEvent.setup();
  markRecallContacted.mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 409, code: "invalid_status", message: "changed" },
  });
  render(<ContactedButton recallId="rc-1" view="all" page={2} />);

  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/recalls?view=all&page=2&notice=changed");
  });
});

test("an inactive patient shows a message instead of the changed notice", async () => {
  const user = userEvent.setup();
  markRecallContacted.mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 409, code: "patient_inactive", message: "inactive" },
  });
  render(<ContactedButton recallId="rc-1" view="due" page={1} />);

  await user.click(screen.getByRole("button", { name: "Mark contacted" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This patient is inactive.");
  expect(push).not.toHaveBeenCalled();
});
