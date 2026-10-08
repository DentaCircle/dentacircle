import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { MainNav } from "@/components/main-nav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/patients/new",
}));

test("patients stays current on the new-patient page", () => {
  render(<MainNav />);

  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
});
