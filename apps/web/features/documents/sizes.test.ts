import { expect, test } from "vitest";

import { fileProblem, MAX_UPLOAD_BYTES, sizeLabel, typeLabel } from "@/features/documents/sizes";

const PDF_BYTES = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]);
const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const JPEG_BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0]);

function syntheticFile(bytes: Uint8Array, name: string, type = ""): File {
  return new File([bytes], name, { type });
}

test("the limit is 8 MiB, the same as the API", () => {
  expect(MAX_UPLOAD_BYTES).toBe(8_388_608);
});

test("an allowed type up to the limit has no problem", async () => {
  await expect(fileProblem(syntheticFile(PDF_BYTES, "a.pdf"))).resolves.toBeNull();
  await expect(fileProblem(syntheticFile(PNG_BYTES, "a.png", "image/png"))).resolves.toBeNull();
  const atLimit = syntheticFile(JPEG_BYTES, "a.jpg");
  Object.defineProperty(atLimit, "size", { value: MAX_UPLOAD_BYTES });
  await expect(fileProblem(atLimit)).resolves.toBeNull();
});

test("a valid PDF is accepted when the browser leaves MIME type empty", async () => {
  await expect(fileProblem(syntheticFile(PDF_BYTES, "scan.pdf", ""))).resolves.toBeNull();
});

test("an empty file, a wrong type and an oversize file are named", async () => {
  await expect(fileProblem(syntheticFile(new Uint8Array(), "empty.pdf"))).resolves.toBe("empty");
  await expect(fileProblem(syntheticFile(new Uint8Array([0x47, 0x49, 0x46]), "a.gif"))).resolves.toBe(
    "type",
  );
  const tooBig = syntheticFile(PDF_BYTES, "big.pdf");
  Object.defineProperty(tooBig, "size", { value: MAX_UPLOAD_BYTES + 1 });
  await expect(fileProblem(tooBig)).resolves.toBe("size");
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
