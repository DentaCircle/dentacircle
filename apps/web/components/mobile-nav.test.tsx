import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { MobileNav } from "@/components/mobile-nav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/status",
}));

test("menu button opens the sheet and a link closes it", async () => {
  const user = userEvent.setup();
  render(<MobileNav />);

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Open menu" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Status" })).toHaveAttribute("aria-current", "page");

  await user.click(screen.getByRole("link", { name: "Dashboard" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
