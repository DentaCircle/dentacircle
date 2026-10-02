import { afterEach, describe, expect, test, vi } from "vitest";

import { getHealth, getReadiness } from "@/lib/api/client";
import { GENERIC_ERROR_MESSAGE } from "@/lib/api/errors";

const marker = "synthetic-marker-raw-body";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getHealth", () => {
  test("returns the parsed body on 200 and times out after 5 seconds", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    stubFetch(jsonResponse(200, { status: "ok" }));

    await expect(getHealth()).resolves.toEqual({ ok: true, data: { status: "ok" } });
    expect(timeout).toHaveBeenCalledWith(5_000);
  });

  test("returns an api error for the standard error shape", async () => {
    stubFetch(
      jsonResponse(503, {
        error: { code: "service_unavailable", message: "Database is not ready.", request_id: "req-1" },
      }),
    );

    await expect(getReadiness()).resolves.toEqual({
      ok: false,
      error: {
        kind: "api",
        status: 503,
        code: "service_unavailable",
        message: "Database is not ready.",
        requestId: "req-1",
      },
    });
  });

  test("uses a generic message when the error body is not JSON", async () => {
    stubFetch({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error(marker)),
    });

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toEqual({
        kind: "api",
        status: 500,
        code: "invalid_response",
        message: GENERIC_ERROR_MESSAGE,
        requestId: "",
      });
    }
    expect(JSON.stringify(result)).not.toContain(marker);
  });

  test("uses a generic message when the error body is the wrong shape", async () => {
    stubFetch(jsonResponse(422, { error: { detail: marker } }));

    const result = await getHealth();

    expect(result.ok).toBe(false);
    if (!result.ok && result.error.kind === "api") {
      expect(result.error.message).toBe(GENERIC_ERROR_MESSAGE);
    }
    expect(JSON.stringify(result)).not.toContain(marker);
  });

  test("returns a network error when fetch fails", async () => {
    stubFetch(Promise.reject(new TypeError("failed")));

    await expect(getHealth()).resolves.toEqual({
      ok: false,
      error: { kind: "network", message: "The API could not be reached." },
    });
  });

  test("returns a timeout error when the request is aborted", async () => {
    stubFetch(Promise.reject(new DOMException("timed out", "TimeoutError")));

    await expect(getHealth()).resolves.toEqual({
      ok: false,
      error: { kind: "timeout", message: "The API did not respond in time." },
    });
  });
});

function jsonResponse(status: number, body: unknown): { ok: boolean; status: number; json: () => Promise<unknown> } {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}

function stubFetch(value: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(value)),
  );
}
