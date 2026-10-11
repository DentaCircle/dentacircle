import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MainNav } from "@/components/main-nav";

const path = vi.hoisted(() => ({ value: "/patients/new" }));

vi.mock("next/navigation", () => ({
  usePathname: () => path.value,
}));

afterEach(() => {
  path.value = "/patients/new";
});

test("patients stays current on the new-patient page", () => {
  render(<MainNav />);

  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
});

test("patients stays current on the detail and edit pages", () => {
  path.value = "/patients/00000000-0000-4000-8000-000000000010";
  const { rerender } = render(<MainNav />);
  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");

  path.value = "/patients/00000000-0000-4000-8000-000000000010/edit";
  rerender(<MainNav />);
  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");
});
