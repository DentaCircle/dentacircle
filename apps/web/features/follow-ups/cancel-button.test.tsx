import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { CancelButton } from "@/features/follow-ups/cancel-button";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());
const cancelFollowUp = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

vi.mock("@/lib/api/client", () => ({
  cancelFollowUp,
}));

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  cancelFollowUp.mockReset();
});

test("keep closes the question without a request", async () => {
  const user = userEvent.setup();
  render(<CancelButton followUpId="fu-1" view="due" page={1} />);

  await user.click(screen.getByRole("button", { name: "Cancel follow-up" }));
  expect(screen.getByText("Cancel this follow-up? This cannot be undone.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep" }));

  expect(screen.getByRole("button", { name: "Cancel follow-up" })).toBeInTheDocument();
  expect(cancelFollowUp).not.toHaveBeenCalled();
});

test("confirm cancels once and reloads with the notice", async () => {
  const user = userEvent.setup();
  let resolveCancel: (value: unknown) => void = () => undefined;
  cancelFollowUp.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveCancel = resolve;
      }),
  );
  render(<CancelButton followUpId="fu-1" view="all" page={2} />);
  await user.click(screen.getByRole("button", { name: "Cancel follow-up" }));

  const yes = screen.getByRole("button", { name: "Yes, cancel" });
  const first = user.click(yes);
  const second = user.click(yes);
  await waitFor(() => expect(cancelFollowUp).toHaveBeenCalledTimes(1));
  resolveCancel({ ok: true, data: null });
  await Promise.all([first, second]);

  expect(cancelFollowUp).toHaveBeenCalledTimes(1);
  expect(cancelFollowUp).toHaveBeenCalledWith("fu-1");
  expect(push).toHaveBeenCalledWith("/follow-ups?view=all&page=2&notice=cancelled");
  expect(refresh).toHaveBeenCalled();
});

test("a 409 refreshes and shows that the follow-up has already changed", async () => {
  const user = userEvent.setup();
  cancelFollowUp.mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 409, code: "invalid_status", message: "changed", requestId: "" },
  });
  render(<CancelButton followUpId="fu-1" view="due" page={1} />);
  await user.click(screen.getByRole("button", { name: "Cancel follow-up" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));

  expect(push).toHaveBeenCalledWith("/follow-ups?page=1&notice=changed");
  expect(refresh).toHaveBeenCalled();
});

test("patient inactive shows an inline message and leaves the button enabled", async () => {
  const user = userEvent.setup();
  cancelFollowUp.mockResolvedValue({
    ok: false,
    error: {
      kind: "api",
      status: 409,
      code: "patient_inactive",
      message: "This patient is inactive.",
      requestId: "",
    },
  });
  render(<CancelButton followUpId="fu-1" view="due" page={1} />);
  await user.click(screen.getByRole("button", { name: "Cancel follow-up" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This patient is inactive.");
  expect(screen.getByRole("button", { name: "Yes, cancel" })).not.toBeDisabled();
  expect(push).not.toHaveBeenCalled();
});

test("forbidden shows that the caller has no access", async () => {
  const user = userEvent.setup();
  cancelFollowUp.mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 403, code: "forbidden", message: "no", requestId: "" },
  });
  render(<CancelButton followUpId="fu-1" view="due" page={1} />);
  await user.click(screen.getByRole("button", { name: "Cancel follow-up" }));
  await user.click(screen.getByRole("button", { name: "Yes, cancel" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("You do not have access.");
  expect(push).not.toHaveBeenCalled();
});
