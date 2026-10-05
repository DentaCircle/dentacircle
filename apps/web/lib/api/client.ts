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

export type { ApiError, ApiResult };

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export function apiBaseUrl(): string {
  const configured = process.env.API_BASE_URL;
  if (configured === undefined || configured.trim() === "") return DEFAULT_API_BASE_URL;
  return configured.replace(/\/$/, "");
}

export function getHealth(): Promise<ApiResult<HealthResponse>> {
  return getJson("/health");
}

export function getReadiness(): Promise<ApiResult<HealthResponse>> {
  return getJson("/health/ready");
}

async function getJson(path: string): Promise<ApiResult<HealthResponse>> {
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      const body: unknown = await readJson(response);
      return { ok: false, error: parseErrorBody(response.status, body) };
    }
    const data = healthData(await readJson(response));
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
