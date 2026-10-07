import {
  genericApiError,
  isTimeoutError,
  NETWORK_ERROR_MESSAGE,
  parseErrorBody,
  REQUEST_TIMEOUT_MS,
  TIMEOUT_ERROR_MESSAGE,
  type ApiError,
  type ApiResult,
} from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type CurrentUser = components["schemas"]["UserResponse"];

export type { ApiError, ApiResult };

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export function apiBaseUrl(): string {
  const configured = process.env.API_BASE_URL;
  if (configured === undefined || configured.trim() === "") return DEFAULT_API_BASE_URL;
  return configured.replace(/\/$/, "");
}

export function getHealth(): Promise<ApiResult<HealthResponse>> {
  return getJson("/health", healthData);
}

export function getReadiness(): Promise<ApiResult<HealthResponse>> {
  return getJson("/health/ready", healthData);
}

export function getCurrentUser(cookieHeader: string): Promise<ApiResult<CurrentUser>> {
  const headers = cookieHeader === "" ? undefined : { cookie: cookieHeader };
  return getJson("/auth/me", currentUserData, headers);
}

async function getJson<T>(
  path: string,
  parse: (value: unknown) => T | null,
  headers?: HeadersInit,
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      cache: "no-store",
      headers,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      const body: unknown = await readJson(response);
      return { ok: false, error: parseErrorBody(response.status, body) };
    }
    const data = parse(await readJson(response));
    if (data === null) return { ok: false, error: genericApiError(response.status) };
    return { ok: true, data };
  } catch (error) {
    if (isTimeoutError(error)) {
      return { ok: false, error: { kind: "timeout", message: TIMEOUT_ERROR_MESSAGE } };
    }
    return { ok: false, error: { kind: "network", message: NETWORK_ERROR_MESSAGE } };
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function healthData(value: unknown): HealthResponse | null {
  if (typeof value !== "object" || value === null || !("status" in value)) return null;
  const status = value.status;
  if (typeof status !== "string") return null;
  const data: HealthResponse = { status };
  return data;
}

function currentUserData(value: unknown): CurrentUser | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const email = stringField(value, "email");
  const fullName = stringField(value, "full_name");
  const roles = stringListField(value, "roles");
  const clinic = isRecord(value.clinic) ? value.clinic : null;
  const clinicId = clinic === null ? null : stringField(clinic, "id");
  const clinicName = clinic === null ? null : stringField(clinic, "name");
  if (id === null || email === null || fullName === null || roles === null || clinicId === null || clinicName === null) {
    return null;
  }
  return {
    id,
    email,
    full_name: fullName,
    roles,
    clinic: { id: clinicId, name: clinicName },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringField(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  if (typeof field !== "string") return null;
  return field;
}

function stringListField(value: Record<string, unknown>, key: string): string[] | null {
  const field = value[key];
  if (!Array.isArray(field) || !field.every((item) => typeof item === "string")) return null;
  return field;
}
