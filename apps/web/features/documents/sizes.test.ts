import { expect, test } from "vitest";

import { fileProblem, MAX_UPLOAD_BYTES, sizeLabel, typeLabel } from "@/features/documents/sizes";

test("the limit is 8 MiB, the same as the API", () => {
  expect(MAX_UPLOAD_BYTES).toBe(8_388_608);
});

test("an allowed type up to the limit has no problem", () => {
  expect(fileProblem({ type: "application/pdf", size: 1 })).toBeNull();
  expect(fileProblem({ type: "image/png", size: 1000 })).toBeNull();
  expect(fileProblem({ type: "image/jpeg", size: MAX_UPLOAD_BYTES })).toBeNull();
});

test("an empty file, a wrong type and an oversize file are named", () => {
  expect(fileProblem({ type: "application/pdf", size: 0 })).toBe("empty");
  expect(fileProblem({ type: "image/gif", size: 10 })).toBe("type");
  expect(fileProblem({ type: "", size: 10 })).toBe("type");
  expect(fileProblem({ type: "application/pdf", size: MAX_UPLOAD_BYTES + 1 })).toBe("size");
});

test("sizes read in B, KB and MB", () => {
  expect(sizeLabel(10)).toBe("10 B");
  expect(sizeLabel(1536)).toBe("1.5 KB");
  expect(sizeLabel(1_048_576)).toBe("1.0 MB");
  expect(sizeLabel(MAX_UPLOAD_BYTES)).toBe("8.0 MB");
});

test("types read as short labels", () => {
  expect(typeLabel("application/pdf")).toBe("PDF");
  expect(typeLabel("image/png")).toBe("PNG");
  expect(typeLabel("image/jpeg")).toBe("JPEG");
});
