import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import NotFound from "@/app/not-found";

test("shows a not-found page with a link home", () => {
  render(<NotFound />);

  expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute("href", "/");
});
