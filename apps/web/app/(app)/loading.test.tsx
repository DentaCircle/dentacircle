import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Loading from "@/app/(app)/loading";

test("announces loading without fabricated counts and respects reduced motion", () => {
  render(<Loading />);
  const status = screen.getByRole("status", { name: "Loading workspace" });
  expect(status).toHaveTextContent("Loading your clinic workspace…");
  expect(status.querySelector("[aria-hidden='true']")).toHaveClass("motion-safe:animate-pulse");
});
