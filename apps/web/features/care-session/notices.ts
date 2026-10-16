export type SessionNotice = "saved" | "session_exists" | "invalid_status" | "item_changed";

export const SESSION_NOTICES: Record<SessionNotice, string> = {
  saved: "Care session saved.",
  session_exists: "A care session was already recorded for this visit.",
  invalid_status: "This visit can no longer take a care session.",
  item_changed: "A care item has already changed.",
};

const SESSION_NOTICE_NAMES: readonly SessionNotice[] = [
  "saved",
  "session_exists",
  "invalid_status",
  "item_changed",
];

export function isSessionNotice(value: string | undefined): value is SessionNotice {
  return SESSION_NOTICE_NAMES.some((notice) => notice === value);
}

export function careSessionHref(appointmentId: string, notice?: SessionNotice): string {
  if (notice === undefined) return `/appointments/${appointmentId}/care`;
  return `/appointments/${appointmentId}/care?notice=${notice}`;
}
