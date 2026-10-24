import { expect, test } from "vitest";

import { canUseDocuments } from "@/features/documents/access";
import {
  documentsHref,
  downloadHref,
  isLinkedToContext,
  pageFromQuery,
} from "@/features/documents/links";
import { documentRow } from "@/features/documents/rows";

test("links are built from the ids", () => {
  expect(documentsHref("p-1")).toBe("/patients/p-1/documents?page=1");
  expect(documentsHref("p-1", 3)).toBe("/patients/p-1/documents?page=3");
  expect(documentsHref("p-1", 1, "uploaded")).toBe("/patients/p-1/documents?page=1&notice=uploaded");
  expect(documentsHref("p-1", 1, undefined, { kind: "visit", id: "visit-1" })).toBe(
    "/patients/p-1/documents?page=1&appointment_id=visit-1",
  );
  expect(documentsHref("p-1", 1, undefined, { kind: "lab", id: "lab-1" })).toBe(
    "/patients/p-1/documents?page=1&lab_work_id=lab-1",
  );
  expect(downloadHref("p-1", "d-1")).toBe("/api/patients/p-1/documents/d-1/file");
});

test("a document linked to this visit or follow-up is not offered again", () => {
  const unlinked = { appointment: null, follow_up: null, lab_work: null };
  const visit = { appointment: { id: "visit-1" }, follow_up: null, lab_work: null };
  const followUp = { appointment: null, follow_up: { id: "fu-1" }, lab_work: null };
  const lab = {
    appointment: null,
    follow_up: null,
    lab_work: { id: "lab-1" },
  };
  expect(isLinkedToContext(unlinked, { kind: "visit", id: "visit-1" })).toBe(false);
  expect(isLinkedToContext(visit, { kind: "visit", id: "visit-1" })).toBe(true);
  expect(isLinkedToContext(visit, { kind: "visit", id: "visit-2" })).toBe(false);
  expect(isLinkedToContext(followUp, { kind: "follow-up", id: "fu-1" })).toBe(true);
  expect(isLinkedToContext(followUp, { kind: "visit", id: "visit-1" })).toBe(false);
  expect(isLinkedToContext(lab, { kind: "lab", id: "lab-1" })).toBe(true);
  expect(isLinkedToContext(unlinked, { kind: "lab", id: "lab-1" })).toBe(false);
});

test("a bad page falls back to 1", () => {
  expect(pageFromQuery(undefined)).toBe(1);
  expect(pageFromQuery("0")).toBe(1);
  expect(pageFromQuery("-2")).toBe(1);
  expect(pageFromQuery("x")).toBe(1);
  expect(pageFromQuery("4")).toBe(4);
});

test("the three roles may use documents and inventory admin may not", () => {
  expect(canUseDocuments(["receptionist"])).toBe(true);
  expect(canUseDocuments(["clinician"])).toBe(true);
  expect(canUseDocuments(["clinic_admin"])).toBe(true);
  expect(canUseDocuments(["inventory_admin"])).toBe(false);
  expect(canUseDocuments([])).toBe(false);
});

test("a row shows clinic wall time as the API sent it", () => {
  const row = documentRow("p-1", {
    id: "d-1",
    filename: "report.pdf",
    content_type: "application/pdf",
    size_bytes: 2048,
    uploaded_at: "2026-10-12T10:05:00+05:30",
    uploaded_by: { id: "u-1", name: "Sample Desk" },
    appointment: {
      id: "visit-1",
      starts_at: "2026-10-12T10:00:00+05:30",
      type_name: "Consultation",
    },
    follow_up: { id: "fu-1", due_on: "2026-10-19" },
    lab_work: { id: "lab-1", title: "Crown", status: "ready" },
  });
  expect(row).toEqual({
    id: "d-1",
    filename: "report.pdf",
    type: "PDF",
    size: "2.0 KB",
    uploadedBy: "Sample Desk",
    uploadedAt: "2026-10-12 10:05",
    href: "/api/patients/p-1/documents/d-1/file",
    viewerHref: "/patients/p-1/documents/d-1",
    links: [
      "Visit: Consultation, 2026-10-12 10:00",
      "Follow-up due 19 Oct 2026",
      "Lab work: Crown, Ready",
    ],
    contentType: "application/pdf",
  });
});
