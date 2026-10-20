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

test("calendar is current on the calendar page", () => {
  path.value = "/calendar";
  render(<MainNav />);

  expect(screen.getByRole("link", { name: "Calendar" })).toHaveAttribute("href", "/calendar");
  expect(screen.getByRole("link", { name: "Calendar" })).toHaveAttribute("aria-current", "page");
});

test("follow-ups stays current on the book page", () => {
  path.value = "/follow-ups/fu-1/book";
  render(<MainNav />);

  expect(screen.getByRole("link", { name: "Follow-ups" })).toHaveAttribute("href", "/follow-ups");
  expect(screen.getByRole("link", { name: "Follow-ups" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Calendar" })).not.toHaveAttribute("aria-current");
});

test("patients stays current on the detail and edit pages", () => {
  path.value = "/patients/00000000-0000-4000-8000-000000000010";
  const { rerender } = render(<MainNav />);
  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");

  path.value = "/patients/00000000-0000-4000-8000-000000000010/edit";
  rerender(<MainNav />);
  expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");
});
