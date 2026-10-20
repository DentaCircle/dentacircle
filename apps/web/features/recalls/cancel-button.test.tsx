import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CancelButton } from "@/features/recalls/cancel-button";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());
const cancelRecall = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/client", () => ({
  cancelRecall,
}));

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  cancelRecall.mockReset();
});

test("keep closes the question without a request", async () => {
  const user = userEvent.setup();
  render(<CancelButton recallId="rc-1" view="due" page={1} />);

  await user.click(screen.getByRole("button", { name: "Cancel recall" }));
  expect(screen.getByText("Cancel this recall? This cannot be undone.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep" }));

  expect(screen.getByRole("button", { name: "Cancel recall" })).toBeInTheDocument();
  expect(cancelRecall).not.toHaveBeenCalled();
});

test("confirm cancels once and reloads with the notice", async () => {
  const user = userEvent.setup();
  let resolveCancel: (value: unknown) => void = () => undefined;
  cancelRecall.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveCancel = resolve;
      }),
  );
  render(<CancelButton recallId="rc-1" view="all" page={2} />);

  await user.click(screen.getByRole("button", { name: "Cancel recall" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));
  expect(cancelRecall).toHaveBeenCalledTimes(1);

  resolveCancel({ ok: true, data: null });
  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/recalls?view=all&page=2&notice=cancelled");
  });
  expect(refresh).toHaveBeenCalled();
});
