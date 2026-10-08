import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import type { CurrentUser } from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const syntheticUser: CurrentUser = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "a@x.test",
  full_name: "Synthetic Person",
  roles: ["clinician"],
  clinic: { id: "00000000-0000-4000-8000-000000000002", name: "Synthetic Clinic" },
};

test("shell shows the app name, the signed-in user, and the current page", () => {
  render(
    <AppShell user={syntheticUser}>
      <p>page body</p>
    </AppShell>,
  );

  expect(screen.getByRole("banner").textContent).toContain("Dentacircle");
  expect(screen.getByRole("banner")).toHaveTextContent("Synthetic Person");
  expect(screen.getByRole("banner")).toHaveTextContent("Synthetic Clinic");
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  expect(screen.getByRole("main")).toBeInTheDocument();
  expect(screen.getByText("page body")).toBeInTheDocument();

  const dashboardLinks = screen.getAllByRole("link", { name: "Dashboard" });
  const statusLinks = screen.getAllByRole("link", { name: "Status" });
  expect(dashboardLinks).toHaveLength(1);
  expect(statusLinks).toHaveLength(1);
  for (const link of dashboardLinks) {
    expect(link).toHaveAttribute("aria-current", "page");
  }
  for (const link of statusLinks) {
    expect(link).not.toHaveAttribute("aria-current");
  }
  const patientLinks = screen.getAllByRole("link", { name: "Patients" });
  expect(patientLinks).toHaveLength(1);
  for (const link of patientLinks) {
    expect(link).toHaveAttribute("href", "/patients");
    expect(link).not.toHaveAttribute("aria-current");
  }
});

test("sidebar is hidden below md and the menu button is hidden from md up", () => {
  render(
    <AppShell user={syntheticUser}>
      <p>page body</p>
    </AppShell>,
  );

  expect(screen.getByRole("complementary").className).toContain("hidden");
  expect(screen.getByRole("complementary").className).toContain("md:block");
  expect(screen.getByRole("button", { name: "Open menu" }).className).toContain("md:hidden");
});
