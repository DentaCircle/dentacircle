import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import TimelinePage from "@/app/(app)/patients/[id]/timeline/page";

const mocks = vi.hoisted(() => ({ user: vi.fn(), patient: vi.fn(), timeline: vi.fn() }));
vi.mock("@/features/auth/current-user", () => ({ requireUser: mocks.user }));
vi.mock("@/features/patients/session", () => ({ sessionCookieHeader: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ getPatient: mocks.patient, listTimeline: mocks.timeline }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user.mockResolvedValue({ roles: ["clinician"] });
  mocks.patient.mockResolvedValue({ ok: true, data: { id: "p1", full_name: "Synthetic Patient", display_id: "P-0001" } });
  mocks.timeline.mockResolvedValue({ ok: true, data: { items: [], total: 0, page: 1, page_size: 20 } });
});

const props = { params: Promise.resolve({ id: "p1" }), searchParams: Promise.resolve({}) };

test("timeline loads identity once and shows active patient navigation", async () => {
  render(await TimelinePage(props));
  expect(screen.getByText("Synthetic Patient")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
  expect(mocks.patient).toHaveBeenCalledExactlyOnceWith("session", "p1");
});

test("a role without access does not request patient identity", async () => {
  mocks.user.mockResolvedValue({ roles: ["inventory_admin"] });
  render(await TimelinePage(props));
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(mocks.patient).not.toHaveBeenCalled();
  expect(mocks.timeline).not.toHaveBeenCalled();
});

test("reports missing identity while retaining the timeline empty state", async () => {
  mocks.patient.mockResolvedValue({ ok: false, error: { kind: "network" } });
  render(await TimelinePage(props));
  expect(screen.getByRole("alert")).toHaveTextContent("Patient details could not be loaded.");
  expect(screen.queryByRole("navigation", { name: "Patient sections" })).not.toBeInTheDocument();
  expect(screen.getByText("Nothing has happened for this patient yet.")).toBeInTheDocument();
});
