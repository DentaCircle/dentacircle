import { expect, test } from "vitest";

import { calendarHref, datesInView, readCalendarQuery, stepDate } from "@/features/calendar/links";

const clinicians = ["clinician-1"];

test("a bad view, date, clinician or notice falls back without an error", () => {
  expect(
    readCalendarQuery(
      { view: "month", date: "nope", clinician: "missing", notice: "nope" },
      "2026-10-14",
      clinicians,
    ),
  ).toEqual({ view: "day", date: "2026-10-14", clinician: null, notice: null });
  expect(
    readCalendarQuery({ date: "2026-02-31", clinician: "", notice: "" }, "2026-10-14", clinicians),
  ).toEqual({ view: "day", date: "2026-10-14", clinician: null, notice: null });
});

test("a known view, date, clinician and notice are kept", () => {
  expect(
    readCalendarQuery(
      { view: "week", date: "2026-10-16", clinician: "clinician-1", notice: "cancelled" },
      "2026-10-14",
      clinicians,
    ),
  ).toEqual({ view: "week", date: "2026-10-16", clinician: "clinician-1", notice: "cancelled" });
});

test("previous, next and today keep the view and clinician", () => {
  expect(stepDate("2026-10-14", "day", -1)).toBe("2026-10-13");
  expect(stepDate("2026-10-14", "day", 1)).toBe("2026-10-15");
  expect(stepDate("2026-10-14", "week", -1)).toBe("2026-10-07");
  expect(stepDate("2026-10-14", "week", 1)).toBe("2026-10-21");
  expect(calendarHref({ view: "week", date: "2026-10-14", clinician: "clinician-1" })).toBe(
    "/calendar?view=week&date=2026-10-14&clinician=clinician-1",
  );
  expect(calendarHref({ view: "day", date: "2026-10-14", clinician: null })).toBe(
    "/calendar?view=day&date=2026-10-14",
  );
});

test("day and week toggles keep the date and clinician", () => {
  const date = "2026-10-16";
  const clinician = "clinician-1";
  expect(calendarHref({ view: "day", date, clinician })).toContain("view=day");
  expect(calendarHref({ view: "week", date, clinician })).toBe(
    "/calendar?view=week&date=2026-10-16&clinician=clinician-1",
  );
});

test("a week is Monday to Sunday", () => {
  expect(datesInView("week", "2026-10-14")).toEqual([
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-17",
    "2026-10-18",
  ]);
  expect(datesInView("day", "2026-10-14")).toEqual(["2026-10-14"]);
});
