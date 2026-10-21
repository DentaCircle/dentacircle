import { REQUEST_TIMEOUT_MS } from "@/lib/api/errors";

/** Sends one request with the shared timeout, optionally cancelled by the caller. */
export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  cancellation?: AbortSignal,
): Promise<Response> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
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
