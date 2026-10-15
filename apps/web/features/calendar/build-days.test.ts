import { expect, test } from "vitest";

import { buildDays } from "@/features/calendar/build-days";
import type { CalendarVisit } from "@/lib/api/client";

test("a visit that starts the day before is shown on the first listed day", () => {
  const days = buildDays(["2026-10-25"], [visit("2026-10-24T23:30:00+01:00", "2026-10-25T00:20:00+01:00")], "2026-10-25");
  expect(days?.[0]?.visits[0]?.timeRange).toBe("23:30–00:20");
  expect(days?.[0]?.isToday).toBe(true);
});

function visit(startsAt: string, endsAt: string): CalendarVisit {
  return {
    id: "visit-1",
    starts_at: startsAt,
    ends_at: endsAt,
    status: "scheduled",
    patient: { id: "patient-1", full_name: "Sample Ada", display_id: "P-0001" },
    clinician: { id: "clinician-1", full_name: "Sample Clinician" },
    appointment_type: { id: "type-1", name: "Consultation" },
  };
}
