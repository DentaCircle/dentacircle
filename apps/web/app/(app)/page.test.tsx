import { beforeEach, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import HomePage from "@/app/(app)/page";
import { requireUser } from "@/features/auth/current-user";

vi.mock("@/features/auth/current-user", () => ({
  requireUser: vi.fn(),
}));

const syntheticUser = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "a@x.test",
  full_name: "Synthetic Person",
  roles: ["clinician", "receptionist"],
  clinic: { id: "00000000-0000-4000-8000-000000000002", name: "Synthetic Clinic" },
};

beforeEach(() => {
  vi.mocked(requireUser).mockResolvedValue(syntheticUser);
});

test("shows the signed-in user's name, roles and clinic", async () => {
  render(await HomePage());

  expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  expect(screen.getByText("Synthetic Person")).toBeInTheDocument();
  expect(screen.getByText("Synthetic Clinic")).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Roles" })).toBeInTheDocument();
  expect(screen.getByText("clinician")).toBeInTheDocument();
  expect(screen.getByText("receptionist")).toBeInTheDocument();
});
