export const GENERIC_ERROR_MESSAGE = "The response could not be read.";
export const NETWORK_ERROR_MESSAGE = "The API could not be reached.";
export const TIMEOUT_ERROR_MESSAGE = "The API did not respond in time.";
export const REQUEST_TIMEOUT_MS = 5_000;

export type ApiError =
  | {
      kind: "api";
      status: number;
      code: string;
      message: string;
      requestId: string;
    }
  | { kind: "network"; message: string }
  | { kind: "timeout"; message: string };

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

type ErrorShape = {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
};

export function genericApiError(status: number): ApiError {
  return {
    kind: "api",
    status,
    code: "invalid_response",
    message: GENERIC_ERROR_MESSAGE,
    requestId: "",
  };
}

export function parseErrorBody(status: number, body: unknown): ApiError {
  if (!isErrorShape(body)) return genericApiError(status);
  return {
    kind: "api",
    status,
    code: body.error.code,
    message: body.error.message,
    requestId: body.error.request_id,
  };
}

function isErrorShape(body: unknown): body is ErrorShape {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = body.error;
  if (typeof error !== "object" || error === null) return false;
  if (!("code" in error) || !("message" in error) || !("request_id" in error)) return false;
  return (
    typeof error.code === "string" &&
    typeof error.message === "string" &&
    typeof error.request_id === "string"
  );
}

export function isTimeoutError(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError");
}
