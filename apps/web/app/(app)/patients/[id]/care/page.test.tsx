import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import CarePage from "@/app/(app)/patients/[id]/care/page";

const mocks = vi.hoisted(() => ({ user: vi.fn(), patient: vi.fn(), plans: vi.fn(), followUp: vi.fn() }));
vi.mock("@/features/auth/current-user", () => ({ requireUser: mocks.user }));
vi.mock("@/features/patients/session", () => ({ sessionCookieHeader: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ getPatient: mocks.patient, listCarePlans: mocks.plans, getFollowUp: mocks.followUp }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user.mockResolvedValue({ roles: ["clinician"] });
  mocks.patient.mockResolvedValue({ ok: true, data: { id: "p1", full_name: "Synthetic Patient", display_id: "P-0001" } });
  mocks.plans.mockResolvedValue({ ok: true, data: [] });
  mocks.followUp.mockResolvedValue({ ok: true, data: { follow_up: null } });
});
const props = { params: Promise.resolve({ id: "p1" }), searchParams: Promise.resolve({}) };

test("care shows the identity and active section using one patient read", async () => {
  render(await CarePage(props));
  expect(screen.getByText("Synthetic Patient")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Care" })).toHaveAttribute("aria-current", "page");
  expect(mocks.patient).toHaveBeenCalledExactlyOnceWith("session", "p1");
});

test("a role without access does not fetch patient details", async () => {
  mocks.user.mockResolvedValue({ roles: ["inventory_admin"] });
  render(await CarePage(props));
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(mocks.patient).not.toHaveBeenCalled();
  expect(mocks.plans).not.toHaveBeenCalled();
});
