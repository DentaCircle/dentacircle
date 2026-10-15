import { expect, test } from "vitest";

import { dayHeading, mondayOfWeek } from "@/features/calendar/dates";

test("the week starts on Monday", () => {
  expect(mondayOfWeek("2026-10-14")).toBe("2026-10-12");
  expect(mondayOfWeek("2026-10-12")).toBe("2026-10-12");
  expect(mondayOfWeek("2026-10-18")).toBe("2026-10-12");
});

test("a day heading reads like Mon 12 Oct", () => {
  expect(dayHeading("2026-10-12")).toBe("Mon 12 Oct");
  expect(dayHeading("2026-10-02")).toBe("Fri 2 Oct");
});
