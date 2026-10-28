import { beforeEach, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import HomePage from "@/app/(app)/page";
import { requireUser } from "@/features/auth/current-user";
import { loadDashboard } from "@/features/dashboard/load-dashboard";
import type { CurrentUser } from "@/lib/api/client";

vi.mock("@/features/auth/current-user", () => ({ requireUser: vi.fn() }));
vi.mock("@/features/patients/session", () => ({ sessionCookieHeader: vi.fn().mockResolvedValue("dc_session=synthetic") }));
vi.mock("@/features/dashboard/load-dashboard", () => ({ loadDashboard: vi.fn() }));

const syntheticUser: CurrentUser = {
  id: "synthetic-user", email: "a@x.test", full_name: "Synthetic Person", roles: ["clinician", "receptionist"],
  clinic: { id: "synthetic-clinic", name: "Synthetic Clinic" },
};

beforeEach(() => {
  vi.mocked(requireUser).mockResolvedValue(syntheticUser);
  vi.mocked(loadDashboard).mockResolvedValue({ mode: "coordination", today: "2026-10-26", timezone: "Asia/Kolkata", appointments: [], followUps: { items: [], total: 0, page: 1, page_size: 20 }, recalls: { items: [], total: 0, page: 1, page_size: 20 }, lab: { items: [], total: 0, page: 1, page_size: 20 } });
});

test("loads the dashboard with the authenticated user and session", async () => {
  render(await HomePage());
  expect(loadDashboard).toHaveBeenCalledWith(syntheticUser, "dc_session=synthetic");
  expect(screen.getByRole("heading", { name: "Dashboard." })).toBeInTheDocument();
  expect(screen.getByText("Synthetic Person")).toBeInTheDocument();
  expect(screen.getByText("Synthetic Clinic")).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Roles" })).toHaveTextContent("clinician");
  expect(screen.getByRole("list", { name: "Roles" })).toHaveTextContent("receptionist");
});
