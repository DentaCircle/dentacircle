import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import AppError from "@/app/error";

test("shows fixed text and never the exception message", async () => {
  const user = userEvent.setup();
  const reset = vi.fn();
  render(<AppError error={new Error("synthetic-marker-raw-body")} reset={reset} />);

  expect(screen.getByText("The page could not be shown.")).toBeInTheDocument();
  expect(screen.queryByText("synthetic-marker-raw-body")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledOnce();
});
