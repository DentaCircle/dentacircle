import type { ApiError } from "@/lib/api/errors";

export type LabNotice = "added" | "ready" | "collected" | "cancelled" | "changed";

export const LAB_NOTICES: Record<LabNotice, string> = {
  added: "Lab work added.",
  ready: "Marked ready. Active patients are added to the Follow-ups queue.",
  collected: "Marked collected.",
  cancelled: "Lab work cancelled.",
  changed: "That lab work has already changed.",
};

export function isLabNotice(value: string | undefined): value is LabNotice {
  return (
    value === "added" ||
    value === "ready" ||
    value === "collected" ||
    value === "cancelled" ||
    value === "changed"
  );
}

export const ENTER_A_TITLE = "Enter a title.";

/** Fixed text only. A server message or a title is never shown. */
export function labFailure(error: ApiError): string {
  if (error.kind === "timeout") return "The change took too long. Try again.";
  if (error.kind === "network") return "The change could not reach the server. Try again.";
  if (error.status === 409 && error.code === "patient_inactive") {
    return "This patient is inactive.";
  }
  if (error.status === 409 && error.code === "invalid_status") return LAB_NOTICES.changed;
  if (error.status === 403) return "You do not have access.";
  if (error.status === 404) return "Not found.";
  if (error.status === 422) return "Check the title and the expected date.";
  return "Something went wrong.";
}
