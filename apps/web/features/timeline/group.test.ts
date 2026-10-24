import { expect, test } from "vitest";

import { groupByDay } from "@/features/timeline/group";
import { entryHref } from "@/features/timeline/links";
import type { TimelineItem } from "@/lib/api/client";

test("newest first stays grouped by clinic-local day", () => {
  const groups = groupByDay([
    event("later", "2026-10-13T09:15:00+05:30"),
    event("same-morning", "2026-10-12T18:00:00+05:30"),
    event("same-earlier", "2026-10-12T10:00:00+05:30"),
  ]);
  expect(groups.map((group) => group.heading)).toEqual(["Tue 13 Oct", "Mon 12 Oct"]);
  expect(groups[1]?.items.map((item) => item.id)).toEqual(["same-morning", "same-earlier"]);
});

test("a visit links to that calendar day and care links to the care page", () => {
  const patientId = "patient-1";
  const visit = event("visit", "2026-10-12T10:00:00+05:30", "visit_completed");
  const care = event("care", "2026-10-12T10:05:00+05:30", "care_item_completed");
  const followUp = event("follow-up", "2026-10-12T10:06:00+05:30", "follow_up_created");
  const uploaded = event("uploaded", "2026-10-12T10:07:00+05:30", "document_uploaded");
  expect(entryHref(patientId, visit)).toBe("/calendar?view=day&date=2026-10-12");
  expect(entryHref(patientId, care)).toBe("/patients/patient-1/care");
  expect(entryHref(patientId, followUp)).toBeNull();
  expect(entryHref(patientId, uploaded)).toBe("/patients/patient-1/documents/doc-1");
  const lab = event("lab", "2026-10-12T10:08:00+05:30", "lab_work_created");
  expect(entryHref(patientId, lab)).toBe("/patients/patient-1/lab");
});

function event(
  id: string,
  occurredAt: string,
  kind: TimelineItem["kind"] = "patient_registered",
): TimelineItem {
  const subject =
    kind.startsWith("visit_")
      ? {
          appointment_id: "visit-1",
          type_name: "Scaling",
          clinician_name: "Dr Rao",
          starts_at: occurredAt,
        }
      : kind.startsWith("care_")
        ? { name: "Scaling" }
        : kind.startsWith("follow_up_")
          ? { due_on: "2026-10-19" }
          : kind === "document_uploaded"
            ? { document_id: "doc-1", filename: "report.pdf" }
            : kind.startsWith("lab_work_")
              ? { lab_work_id: "lab-1", title: "Crown" }
              : null;
  return {
    id,
    kind,
    occurred_at: occurredAt,
    actor: { id: "user-1", name: "Dr Rao" },
    subject,
  };
}
