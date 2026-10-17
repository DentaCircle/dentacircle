import { expect, test } from "vitest";

import { isSessionNotice } from "@/features/care-session/notices";

test("an unknown notice is ignored", () => {
  expect(isSessionNotice("saved")).toBe(true);
  expect(isSessionNotice("item_changed")).toBe(true);
  expect(isSessionNotice("nope")).toBe(false);
  expect(isSessionNotice(undefined)).toBe(false);
});
