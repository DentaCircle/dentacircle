import { afterEach, describe, expect, test, vi } from "vitest";

import { getCurrentUser, getHealth, getReadiness, listPatients } from "@/lib/api/client";
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

describe("getCurrentUser", () => {
  test("forwards the session cookie to /auth/me", async () => {
    const fetchMock = stubFetch(jsonResponse(200, syntheticUser));

    await expect(getCurrentUser("dc_session=token")).resolves.toEqual({ ok: true, data: syntheticUser });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/auth/me",
      expect.objectContaining({
        cache: "no-store",
        headers: { cookie: "dc_session=token" },
      }),
    );
  });

  test("omits the cookie header when there is no session", async () => {
    const fetchMock = stubFetch(jsonResponse(401, { error: { code: "unauthenticated", message: "Sign in required.", request_id: "req-1" } }));

    const result = await getCurrentUser("");

    expect(result.ok).toBe(false);
    if (!result.ok && result.error.kind === "api") expect(result.error.status).toBe(401);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.headers).toBeUndefined();
  });

  test("returns an error when the body is not a user and does not keep the raw text", async () => {
    stubFetch(jsonResponse(200, { email: "a@x.test", full_name: marker }));

    const result = await getCurrentUser("dc_session=token");

    expect(result.ok).toBe(false);
    if (!result.ok && result.error.kind === "api") {
      expect(result.error.message).toBe(GENERIC_ERROR_MESSAGE);
    }
    expect(JSON.stringify(result)).not.toContain(marker);
  });
});

describe("listPatients", () => {
  test("asks for one page and parses the list", async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, {
        items: [
          {
            id: "00000000-0000-4000-8000-000000000010",
            patient_number: 1,
            display_id: "P-0001",
            full_name: "Sample Ada",
            phone: "9000000001",
            date_of_birth: null,
            created_at: "2026-10-08T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    );

    const result = await listPatients("dc_session=token", 2, "ada");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/patients?page=2&page_size=20&q=ada",
      expect.objectContaining({ headers: { cookie: "dc_session=token" } }),
    );
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.items[0]?.display_id).toBe("P-0001");
  });

  test("does not keep a raw body that is not a patient list", async () => {
    stubFetch(jsonResponse(200, { items: [{ full_name: marker }] }));

    const result = await listPatients("dc_session=token", 1, "");

    expect(result.ok).toBe(false);
    expect(JSON.stringify(result)).not.toContain(marker);
  });
});

const syntheticUser = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "a@x.test",
  full_name: "Synthetic Person",
  roles: ["clinician"],
  clinic: { id: "00000000-0000-4000-8000-000000000002", name: "Synthetic Clinic" },
};

function jsonResponse(status: number, body: unknown): { ok: boolean; status: number; json: () => Promise<unknown> } {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}

function stubFetch(value: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(() => Promise.resolve(value));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
