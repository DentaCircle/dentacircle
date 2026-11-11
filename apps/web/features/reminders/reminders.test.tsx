import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ReminderActions } from "@/features/reminders/actions";
import { clinicInstant, ScheduleButton } from "@/features/reminders/schedule-button";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
afterEach(() => { vi.unstubAllGlobals(); refresh.mockReset(); });

test("converts clinic time and rejects missing or ambiguous daylight times", () => {
  expect(clinicInstant("2026-11-10T10:00", "Asia/Kolkata")).toBe("2026-11-10T04:30:00.000Z");
  expect(clinicInstant("2026-03-08T02:30", "America/New_York")).toBeNull();
  expect(clinicInstant("2026-11-01T01:30", "America/New_York")).toBeNull();
});

test("schedules now and reports a stale conflict", async () => {
  const user = userEvent.setup();
  const fetcher = vi.fn().mockResolvedValue({ ok: false, status: 409 });
  vi.stubGlobal("fetch", fetcher);
  render(<ScheduleButton appointmentId="a1" timezone="Asia/Kolkata" />);
  await user.click(screen.getByRole("button", { name: "Schedule reminder" }));
  await user.click(screen.getByRole("button", { name: "Schedule" }));
  expect(fetcher).toHaveBeenCalledWith("/api/appointments/a1/reminders", expect.objectContaining({ body: "{}" }));
  expect(await screen.findByRole("status")).toHaveTextContent("already has a pending reminder");
});

test("completion refreshes and cancellation conflict explains stale state", async () => {
  const user = userEvent.setup();
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ ok: false, status: 409 });
  vi.stubGlobal("fetch", fetcher);
  render(<ReminderActions id="r1" />);
  await user.click(screen.getByRole("button", { name: "Complete" }));
  expect(refresh).toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("has changed");
});
