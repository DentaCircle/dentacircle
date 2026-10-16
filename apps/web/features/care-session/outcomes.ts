import type { ApiError } from "@/lib/api/errors";

import type { SessionNotice } from "@/features/care-session/notices";

export type SessionFailure =
  | { kind: "reload"; notice: SessionNotice }
  | { kind: "form"; message: string };

export function sessionFailure(error: ApiError): SessionFailure {
  if (error.kind !== "api") return { kind: "form", message: "Something went wrong." };
  if (error.status === 403) return { kind: "form", message: "You do not have access." };
  if (error.status === 409 && error.code === "session_exists") {
    return { kind: "reload", notice: "session_exists" };
  }
  if (error.status === 409 && error.code === "invalid_status") {
    return { kind: "reload", notice: "invalid_status" };
  }
  if (error.status === 409 && error.code === "item_changed") {
    return { kind: "reload", notice: "item_changed" };
  }
  return { kind: "form", message: "Something went wrong." };
}
