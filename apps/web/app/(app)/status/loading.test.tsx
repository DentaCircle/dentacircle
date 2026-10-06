import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import StatusLoading from "@/app/(app)/status/loading";

test("shows a loading message while status is checked", () => {
  render(<StatusLoading />);

  expect(screen.getByText("Checking status")).toBeInTheDocument();
});
