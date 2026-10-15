import { expect, test } from "vitest";

import { isCareNotice } from "@/features/care/notices";

test("an unknown notice is ignored", () => {
  expect(isCareNotice("plan_added")).toBe(true);
  expect(isCareNotice("changed")).toBe(true);
  expect(isCareNotice("nope")).toBe(false);
  expect(isCareNotice(undefined)).toBe(false);
});
