import { afterEach, describe, expect, test, vi } from "vitest";

import {
  cancelFollowUp,
  cancelRecall,
  changeAppointmentStatus,
  getCurrentUser,
  getHealth,
  getPatient,
  getReadiness,
  listAppointments,
  listDocuments,
  listDocumentsInBrowser,
  listPatients,
  uploadDocument,
} from "@/lib/api/client";
import { GENERIC_ERROR_MESSAGE } from "@/lib/api/errors";

const marker = "synthetic-marker-raw-body";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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
            status: "active",
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

  test("sends a status filter", async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      }),
    );

    await listPatients("dc_session=token", 1, "ada", "inactive");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/patients?page=1&page_size=20&q=ada&status=inactive",
      expect.objectContaining({ headers: { cookie: "dc_session=token" } }),
    );
  });
});

describe("getPatient", () => {
  test("parses one patient", async () => {
    stubFetch(
      jsonResponse(200, {
        id: "00000000-0000-4000-8000-000000000010",
        patient_number: 1,
        display_id: "P-0001",
        full_name: "Sample Ada",
        phone: "9000000001",
        date_of_birth: null,
        status: "inactive",
        created_at: "2026-10-08T00:00:00Z",
      }),
    );

    const result = await getPatient("dc_session=token", "00000000-0000-4000-8000-000000000010");

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.status).toBe("inactive");
  });

  test("does not keep a body that is not a patient", async () => {
    stubFetch(jsonResponse(200, { full_name: marker, status: "active" }));

    const result = await getPatient("dc_session=token", "00000000-0000-4000-8000-000000000010");

    expect(result.ok).toBe(false);
    expect(JSON.stringify(result)).not.toContain(marker);
  });
});

describe("listAppointments", () => {
  test("asks for the range and a clinician", async () => {
    const fetchMock = stubFetch(jsonResponse(200, []));

    const result = await listAppointments("dc_session=token", "2026-10-12", "2026-10-18", "clinician-1");

    expect(result).toEqual({ ok: true, data: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/appointments?from=2026-10-12&to=2026-10-18&clinician_id=clinician-1",
      expect.objectContaining({ headers: { cookie: "dc_session=token" } }),
    );
  });
});

describe("changeAppointmentStatus", () => {
  test("posts the target to the same-origin status route", async () => {
    const fetchMock = stubFetch(jsonResponse(200, {}));

    await expect(changeAppointmentStatus("visit-1", "arrived")).resolves.toEqual({
      ok: true,
      data: null,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/appointments/visit-1/status",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({ status: "arrived" }),
      }),
    );
  });

  test("returns a timeout or a network error without throwing", async () => {
    stubFetch(Promise.reject(new DOMException("timed out", "TimeoutError")));
    await expect(changeAppointmentStatus("visit-1", "arrived")).resolves.toEqual({
      ok: false,
      error: { kind: "timeout", message: "The API did not respond in time." },
    });

    stubFetch(Promise.reject(new TypeError("failed")));
    await expect(changeAppointmentStatus("visit-1", "no_show")).resolves.toEqual({
      ok: false,
      error: { kind: "network", message: "The API could not be reached." },
    });
  });
});

describe("cancelRecall", () => {
  test("posts with no body and treats 204 as success", async () => {
    const fetchMock = stubFetch({ ok: true, status: 204, json: () => Promise.resolve(null) });

    await expect(cancelRecall("rc-1")).resolves.toEqual({ ok: true, data: null });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/recalls/rc-1/cancel",
      expect.objectContaining({ method: "POST", credentials: "same-origin" }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeUndefined();
  });
});

describe("cancelFollowUp", () => {
  test("posts with no body and treats 204 as success", async () => {
    const fetchMock = stubFetch({ ok: true, status: 204, json: () => Promise.resolve(null) });

    await expect(cancelFollowUp("fu-1")).resolves.toEqual({ ok: true, data: null });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/follow-ups/fu-1/cancel",
      expect.objectContaining({ method: "POST", credentials: "same-origin" }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeUndefined();
  });
});

describe("listDocuments", () => {
  const item = {
    id: "doc-1",
    filename: "report.pdf",
    content_type: "application/pdf",
    size_bytes: 20,
    uploaded_at: "2026-10-12T10:05:00+05:30",
    uploaded_by: { id: "user-1", name: "Sample Desk" },
    appointment: null,
    follow_up: null,
    lab_work: null,
  };

  test("reads one page with the session cookie, and uses the 5 second timeout", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    const fetchMock = stubFetch(
      jsonResponse(200, { items: [item], total: 1, page: 1, page_size: 20 }),
    );

    await expect(listDocuments("dc_session=abc", "p 1", 1)).resolves.toEqual({
      ok: true,
      data: { items: [item], total: 1, page: 1, page_size: 20 },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/patients/p%201/documents?page=1&page_size=20",
      expect.objectContaining({ headers: { cookie: "dc_session=abc" } }),
    );
    expect(timeout).toHaveBeenCalledWith(5_000);
  });

  test("a body that is not a document page is a generic error", async () => {
    stubFetch(jsonResponse(200, { items: [{ ...item, content_type: "image/gif" }], total: 1, page: 1, page_size: 20 }));
    const result = await listDocuments("", "p-1", 1);
    expect(result.ok).toBe(false);

    stubFetch(jsonResponse(200, { items: [{ ...item, uploaded_by: null }], total: 1, page: 1, page_size: 20 }));
    expect((await listDocuments("", "p-1", 1)).ok).toBe(false);

    stubFetch(jsonResponse(200, { items: [item] }));
    expect((await listDocuments("", "p-1", 1)).ok).toBe(false);
  });

  test("an API error keeps its status and code", async () => {
    stubFetch(
      jsonResponse(404, { error: { code: "not_found", message: "Not Found", request_id: "r-1" } }),
    );
    const result = await listDocuments("", "p-1", 1);
    expect(result).toEqual({
      ok: false,
      error: { kind: "api", status: 404, code: "not_found", message: "Not Found", requestId: "r-1" },
    });
  });
});

describe("listDocumentsInBrowser", () => {
  test("reads one page through the web proxy", async () => {
    const item = {
      id: "doc-1",
      filename: "report.pdf",
      content_type: "application/pdf",
      size_bytes: 20,
      uploaded_at: "2026-10-12T10:05:00+05:30",
      uploaded_by: { id: "user-1", name: "Sample Desk" },
      appointment: null,
      follow_up: null,
      lab_work: null,
    };
    const fetchMock = stubFetch(
      jsonResponse(200, { items: [item], total: 101, page: 2, page_size: 100 }),
    );

    await expect(listDocumentsInBrowser("p 1", 2, 100)).resolves.toEqual({
      ok: true,
      data: { items: [item], total: 101, page: 2, page_size: 100 },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/patients/p%201/documents?page=2&page_size=100",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
});

describe("uploadDocument", () => {
  const file = new File(["%PDF-1.7"], "My report.pdf", { type: "application/pdf" });

  test("sends the raw file with its type and waits up to 60 seconds", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    const fetchMock = stubFetch(jsonResponse(201, {}));

    await expect(uploadDocument("p 1", file)).resolves.toEqual({ ok: true, data: null });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/patients/p%201/documents",
      expect.objectContaining({
        method: "POST",
        body: file,
        headers: {
          "content-type": "application/pdf",
          "x-document-filename": encodeURIComponent("My report.pdf"),
        },
        credentials: "same-origin",
      }),
    );
    expect(timeout).toHaveBeenCalledWith(60_000);
    expect(timeout).not.toHaveBeenCalledWith(5_000);
  });

  test("keeps the status and code of an API error", async () => {
    stubFetch(
      jsonResponse(413, {
        error: { code: "payload_too_large", message: "That file is too large.", request_id: "r-1" },
      }),
    );
    const result = await uploadDocument("p-1", file);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toMatchObject({ kind: "api", status: 413, code: "payload_too_large" });
    }
  });

  test("returns a timeout or a network error without throwing", async () => {
    stubFetch(Promise.reject(new DOMException("timed out", "TimeoutError")));
    await expect(uploadDocument("p-1", file)).resolves.toEqual({
      ok: false,
      error: { kind: "timeout", message: "The API did not respond in time." },
    });

    stubFetch(Promise.reject(new TypeError("failed")));
    await expect(uploadDocument("p-1", file)).resolves.toEqual({
      ok: false,
      error: { kind: "network", message: "The API could not be reached." },
    });
  });

  test("ordinary calls keep the 5 second timeout", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    stubFetch({ ok: true, status: 200, json: () => Promise.resolve({}) });
    await changeAppointmentStatus("visit-1", "arrived");
    expect(timeout).toHaveBeenCalledWith(5_000);
    expect(timeout).not.toHaveBeenCalledWith(60_000);
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
