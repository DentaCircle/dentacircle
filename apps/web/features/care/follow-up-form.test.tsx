import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { FollowUpForm } from "@/features/care/follow-up-form";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const patientId = "00000000-0000-4000-8000-000000000010";

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("a date is posted and a success refreshes the care page", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) })),
  );
  render(<FollowUpForm patientId={patientId} />);
  await user.type(screen.getByLabelText("Follow-up date"), "2026-10-24");
  await user.click(screen.getByRole("button", { name: "Create follow-up" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith(`/patients/${patientId}/care`));
  expect(refresh).toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledWith(
    `/api/patients/${patientId}/follow-up`,
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ due_on: "2026-10-24" }),
    }),
  );
});

test("a past or distant date shows a plain message", async () => {
  const user = userEvent.setup();
  for (const rule of ["before_today", "beyond_horizon"]) {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 422,
          json: () =>
            Promise.resolve({
              error: { code: "validation_error", message: `body.due_on: ${rule}`, request_id: "r" },
            }),
        }),
      ),
    );
    const view = render(<FollowUpForm patientId={patientId} />);
    await user.type(screen.getByLabelText("Follow-up date"), "2026-10-24");
    await user.click(screen.getByRole("button", { name: "Create follow-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose a date from today through the next year.",
    );
    expect(push).not.toHaveBeenCalled();
    view.unmount();
  }
});

test("an inactive patient stays on the form", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () =>
          Promise.resolve({
            error: { code: "patient_inactive", message: "This patient is inactive.", request_id: "r" },
          }),
      }),
    ),
  );
  render(<FollowUpForm patientId={patientId} />);
  await user.type(screen.getByLabelText("Follow-up date"), "2026-10-24");
  await user.click(screen.getByRole("button", { name: "Create follow-up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This patient is inactive.");
  expect(push).not.toHaveBeenCalled();
});

test("an open follow-up refreshes the page onto the existing line", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () =>
          Promise.resolve({
            error: {
              code: "follow_up_open",
              message: "Already has an open follow-up.",
              request_id: "r",
            },
          }),
      }),
    ),
  );
  render(<FollowUpForm patientId={patientId} />);
  await user.type(screen.getByLabelText("Follow-up date"), "2026-10-24");
  await user.click(screen.getByRole("button", { name: "Create follow-up" }));
  await waitFor(() =>
    expect(push).toHaveBeenCalledWith(`/patients/${patientId}/care?notice=follow_up_open`),
  );
  expect(refresh).toHaveBeenCalled();
});
