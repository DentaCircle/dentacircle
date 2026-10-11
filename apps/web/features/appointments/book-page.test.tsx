import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { BookPage } from "@/features/appointments/book-page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

test("named states replace the form", () => {
  const { rerender } = render(<BookPage status="no-clinicians" />);
  expect(screen.getByText("No clinicians are set up.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Book" })).not.toBeInTheDocument();

  rerender(<BookPage status="inactive" />);
  expect(screen.getByRole("alert")).toHaveTextContent("This patient is inactive.");
  expect(screen.queryByLabelText("Type")).not.toBeInTheDocument();

  rerender(<BookPage status="not-found" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Patient not found");

  rerender(<BookPage status="forbidden" />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<BookPage status="error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
});
