import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { FollowUpBookPage } from "@/features/follow-ups/book-page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

test("named states replace the form", () => {
  const { rerender } = render(<FollowUpBookPage status="closed" />);
  expect(screen.getByRole("alert")).toHaveTextContent("This follow-up is no longer open.");
  expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();

  rerender(<FollowUpBookPage status="forbidden" />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<FollowUpBookPage status="error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
});
