import type { ApiError, ApiResult, HealthResponse } from "@/lib/api/client";

export type StatusView =
  | { state: "ok" }
  | { state: "database_not_ready"; code: string; requestId: string }
  | { state: "unreachable" }
  | { state: "error"; code: string; requestId: string };

export function statusView(
  health: ApiResult<HealthResponse>,
  ready: ApiResult<HealthResponse>,
): StatusView {
  if (!health.ok) return viewForFailure(health.error);
  if (!ready.ok) {
    if (ready.error.kind === "api" && ready.error.status === 503) {
      return {
        state: "database_not_ready",
        code: ready.error.code,
        requestId: ready.error.requestId,
      };
    }
    return viewForFailure(ready.error);
  }
  return { state: "ok" };
}

function viewForFailure(error: ApiError): StatusView {
  if (error.kind === "network" || error.kind === "timeout") return { state: "unreachable" };
  return { state: "error", code: error.code, requestId: error.requestId };
}
