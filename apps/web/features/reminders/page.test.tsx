import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import RemindersPage from "@/app/(app)/reminders/page";

vi.mock("@/features/auth/current-user", () => ({ requireUser: async () => ({ roles: ["receptionist"] }) }));
vi.mock("@/features/patients/session", () => ({ sessionCookieHeader: async () => "dc_session=synthetic" }));
vi.mock("@/lib/api/client", () => ({ apiBaseUrl: () => "http://api", getClinicDay: async () => ({ ok: true, data: { timezone: "Asia/Kolkata" } }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => vi.unstubAllGlobals());

test("distinguishes an empty queue from a load failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0, page: 1, page_size: 20 }) }));
  const first = render(await RemindersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByText("No reminders are due.")).toBeInTheDocument();
  first.unmount();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(await RemindersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
});

test("shows the patient, clinic time, visit link, and actions", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [{ id: "r1", appointment_id: "a1", patient_id: "p1", patient_name: "Sample Patient", due_at: "2026-11-10T04:30:00Z", starts_at: "2026-11-11T04:30:00Z" }], total: 1, page: 1, page_size: 20 }) }));
  render(await RemindersPage({ searchParams: Promise.resolve({ view: "pending" }) }));
  expect(screen.getByRole("link", { name: "Sample Patient" })).toHaveAttribute("href", "/patients/p1");
  expect(screen.getByText(/Due.*10:00 am/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Visit/ })).toHaveAttribute("href", "/calendar?view=day&date=2026-11-11");
  expect(screen.getByRole("button", { name: "Complete" })).toBeInTheDocument();
});
