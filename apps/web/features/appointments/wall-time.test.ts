import { expect, test } from "vitest";

import { addCalendarDays, clinicToday, wallDate, wallTime } from "@/features/appointments/wall-time";

test("wall time is the clock in the string", () => {
  expect(wallTime("2026-10-12T09:15:00+05:30")).toBe("09:15");
  expect(wallDate("2026-10-12T09:15:00+05:30")).toBe("2026-10-12");
  expect(wallTime("not-a-time")).toBeNull();
});

test("clinic today follows the clinic zone", () => {
  const instant = new Date("2026-10-11T20:00:00Z");
  expect(clinicToday("Asia/Kolkata", instant)).toBe("2026-10-12");
  expect(clinicToday("Europe/London", instant)).toBe("2026-10-11");
});

test("adding days stays on the calendar", () => {
  expect(addCalendarDays("2026-10-11", 365)).toBe("2027-10-11");
});
