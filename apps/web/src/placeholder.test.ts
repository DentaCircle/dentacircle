import { expect, test } from "vitest";

import { placeholder } from "./placeholder.js";

test("placeholder returns ok", () => {
  expect(placeholder()).toBe("ok");
});
