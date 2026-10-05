import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import HomePage from "@/app/page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

test("shell shows the app name, existing routes, and the current page", () => {
  render(
    <AppShell>
      <HomePage />
    </AppShell>,
  );

  expect(screen.getByRole("banner").textContent).toContain("Dentacircle");
  expect(screen.getByRole("main")).toBeInTheDocument();
  expect(screen.getByText("nothing to show yet")).toBeInTheDocument();

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
  expect(screen.queryByRole("link", { name: "Patients" })).not.toBeInTheDocument();
});

test("sidebar is hidden below md and the menu button is hidden from md up", () => {
  render(
    <AppShell>
      <HomePage />
    </AppShell>,
  );

  expect(screen.getByRole("complementary").className).toContain("hidden");
  expect(screen.getByRole("complementary").className).toContain("md:block");
  expect(screen.getByRole("button", { name: "Open menu" }).className).toContain("md:hidden");
});
