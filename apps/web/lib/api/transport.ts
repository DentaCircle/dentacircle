import { REQUEST_TIMEOUT_MS } from "@/lib/api/errors";

/**
 * Sends one request with a timeout, optionally cancelled by the caller. The default is the
 * shared timeout. Only a caller with a reason, such as a file upload, passes its own.
 */
export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  cancellation?: AbortSignal,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = cancellation === undefined ? timeout : AbortSignal.any([cancellation, timeout]);
  return fetch(input, { ...init, signal });
}

/** Reads JSON without exposing malformed response text to callers. */
export async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
