import { expect, test } from "vitest";

import { isDocumentNotice, problemMessage, uploadFailure } from "@/features/documents/notices";
import type { ApiError } from "@/lib/api/errors";

function api(status: number, code: string, message = "server text"): ApiError {
  return { kind: "api", status, code, message, requestId: "req-1" };
}

test("each failure has its own fixed text", () => {
  expect(uploadFailure(api(413, "payload_too_large"))).toBe(
    "That file is too large. The limit is 8 MB.",
  );
  expect(uploadFailure(api(415, "unsupported_media_type"))).toBe(
    "Only PDF, PNG and JPEG files are allowed.",
  );
  expect(uploadFailure(api(409, "patient_inactive"))).toBe("This patient is inactive.");
  expect(uploadFailure(api(403, "forbidden"))).toBe("You do not have access.");
  expect(uploadFailure(api(404, "not_found"))).toBe("Patient not found.");
  expect(uploadFailure(api(422, "validation_error"))).toBe("That file or its name is not valid.");
  expect(uploadFailure(api(500, "internal_error"))).toBe("Something went wrong.");
  expect(uploadFailure({ kind: "network", message: "The API could not be reached." })).toBe(
    "The upload could not reach the server. Try again.",
  );
  expect(uploadFailure({ kind: "timeout", message: "The API did not respond in time." })).toBe(
    "The upload took too long. Try again.",
  );
});

test("a server message is never shown", () => {
  expect(uploadFailure(api(500, "internal_error", "secret-filename.pdf"))).not.toContain("secret");
  expect(uploadFailure(api(422, "validation_error", "secret-filename.pdf"))).not.toContain(
    "secret",
  );
});

test("the picker problems match the API texts", () => {
  expect(problemMessage("size")).toBe(uploadFailure(api(413, "payload_too_large")));
  expect(problemMessage("type")).toBe(uploadFailure(api(415, "unsupported_media_type")));
  expect(problemMessage("empty")).toBe("That file is empty.");
});

test("only the known notice is accepted from the address", () => {
  expect(isDocumentNotice("uploaded")).toBe(true);
  expect(isDocumentNotice("linked")).toBe(true);
  expect(isDocumentNotice("unlinked")).toBe(true);
  expect(isDocumentNotice("deleted")).toBe(false);
  expect(isDocumentNotice(undefined)).toBe(false);
});
