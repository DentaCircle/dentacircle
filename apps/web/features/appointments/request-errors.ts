export const PATIENT_BUSY_MESSAGE = "That patient already has an appointment then. Pick another time.";

/** Reads the coded error shape without retaining an untrusted message. */
export function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("error" in body)) return null;
  const error = body.error;
  if (typeof error !== "object" || error === null || !("code" in error)) return null;
  return typeof error.code === "string" ? error.code : null;
}

/** Maps known appointment conflicts to fixed, safe copy. */
export function conflictMessage(code: string | null, slotMessage: string): string {
  return code === "patient_busy" ? PATIENT_BUSY_MESSAGE : slotMessage;
}
