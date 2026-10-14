import { expect, test } from "vitest";

import { clinicianChoices } from "@/features/appointments/clinician-choices";

const assigned = { id: "clinician-1", label: "Sample Clinician" };
const active = [
  { id: "clinician-2", label: "Second Clinician" },
  assigned,
];

test("an active assigned clinician is not added twice", () => {
  expect(clinicianChoices(assigned, active)).toEqual(active);
});

test("an inactive assigned clinician stays available for a time-only move", () => {
  const others = [{ id: "clinician-2", label: "Second Clinician" }];
  expect(clinicianChoices(assigned, others)).toEqual([assigned, ...others]);
  expect(clinicianChoices(assigned, [])).toEqual([assigned]);
});
