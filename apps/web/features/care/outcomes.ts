import type { ApiError } from "@/lib/api/errors";

import { labelError } from "@/features/care/field-errors";
import type { CareNotice } from "@/features/care/notices";

export type CareFailure =
  | { kind: "reload"; notice: CareNotice }
  | { kind: "field"; message: string }
  | { kind: "form"; message: string };

export function careFailure(error: ApiError, field: "title" | "name" | null): CareFailure {
  if (error.kind !== "api") return { kind: "form", message: "Something went wrong." };
  if (error.status === 403) return { kind: "form", message: "You do not have access." };
  if (error.status === 409 && error.code === "invalid_status") {
    return { kind: "reload", notice: "changed" };
  }
  if (error.status === 409 && error.code === "patient_inactive") {
    return { kind: "form", message: "This patient is inactive." };
  }
  if (error.status === 422 && field !== null) {
    return { kind: "field", message: labelError(error.message, field) };
  }
  return { kind: "form", message: "Something went wrong." };
}
