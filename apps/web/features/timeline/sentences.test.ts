import { expect, test } from "vitest";

import { entrySentence } from "@/features/timeline/sentences";
import type { TimelineItem } from "@/lib/api/client";

test("a completed visit reads as the type with the clinician", () => {
  expect(entrySentence(item("visit_completed", visit()))).toBe(
    "Visit completed: Scaling with Dr Rao",
  );
});

test("care, follow-up, recall and registration each have a sentence", () => {
  expect(entrySentence(item("patient_registered", null))).toBe("Patient registered");
  expect(entrySentence(item("care_item_added", { name: "Scaling" }))).toBe(
    "Care item added: Scaling",
  );
  expect(
    entrySentence(
      item("care_session_recorded", {
        care_session_id: "session-1",
        item_names: ["Scaling", "Root canal"],
      }),
    ),
  ).toBe("Care recorded: Scaling, Root canal");
  expect(entrySentence(item("follow_up_created", { due_on: "2026-10-19" }))).toBe(
    "Follow-up created, due 19 Oct 2026",
  );
  expect(
    entrySentence(item("recall_created", { due_on: "2027-04-12", type_name: "Scaling" })),
  ).toBe("Recall created: Scaling, due 12 Apr 2027");
});

function item(kind: TimelineItem["kind"], subject: TimelineItem["subject"]): TimelineItem {
  return {
    id: "event-1",
    kind,
    occurred_at: "2026-10-12T10:00:00+05:30",
    actor: { id: "user-1", name: "Dr Rao" },
    subject,
  };
}

function visit(): TimelineItem["subject"] {
  return {
    appointment_id: "visit-1",
    type_name: "Scaling",
    clinician_name: "Dr Rao",
    starts_at: "2026-10-12T10:00:00+05:30",
  };
}
