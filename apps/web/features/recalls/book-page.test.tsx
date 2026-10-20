import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { RecallBookPage } from "@/features/recalls/book-page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

test("named states replace the form", () => {
  const { rerender } = render(<RecallBookPage status="closed" />);
  expect(screen.getByRole("alert")).toHaveTextContent("This recall is no longer open.");
  expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();

  rerender(<RecallBookPage status="forbidden" />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<RecallBookPage status="error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
});
