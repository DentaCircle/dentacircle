import type { ApiError } from "@/lib/api/errors";
import type { FileProblem } from "@/features/documents/sizes";

export type DocumentNotice = "uploaded" | "linked" | "unlinked";

export const DOCUMENT_NOTICES: Record<DocumentNotice, string> = {
  uploaded: "Document uploaded.",
  linked: "Document linked.",
  unlinked: "Document unlinked.",
};

export function isDocumentNotice(value: string | undefined): value is DocumentNotice {
  return value === "uploaded" || value === "linked" || value === "unlinked";
}

const TOO_LARGE = "That file is too large. The limit is 8 MB.";
const WRONG_TYPE = "Only PDF, PNG and JPEG files are allowed.";
const EMPTY = "That file is empty.";

export const CHOOSE_A_FILE = "Choose a file first.";

/** Fixed text only. A server message or a file name is never shown. */
export function problemMessage(problem: FileProblem): string {
  if (problem === "empty") return EMPTY;
  if (problem === "type") return WRONG_TYPE;
  return TOO_LARGE;
}

export function uploadFailure(error: ApiError): string {
  if (error.kind === "timeout") return "The upload took too long. Try again.";
  if (error.kind === "network") return "The upload could not reach the server. Try again.";
  if (error.status === 413) return TOO_LARGE;
  if (error.status === 415) return WRONG_TYPE;
  if (error.status === 409 && error.code === "patient_inactive") {
    return "This patient is inactive.";
  }
  if (error.status === 403) return "You do not have access.";
  if (error.status === 404) return "Patient not found.";
  if (error.status === 422) return "That file or its name is not valid.";
  return "Something went wrong.";
}

/** Fixed text only. A server message, a file name or an id is never shown. */
export function linkFailure(error: ApiError): string {
  if (error.kind === "timeout") return "The change took too long. Try again.";
  if (error.kind === "network") return "The change could not reach the server. Try again.";
  if (error.status === 409 && error.code === "patient_inactive") {
    return "This patient is inactive.";
  }
  if (error.status === 403) return "You do not have access.";
  if (error.status === 404) return "Not found.";
  if (error.status === 422) return "That link is not valid.";
  return "Something went wrong.";
}
