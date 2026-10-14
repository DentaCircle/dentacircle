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
export type Patient = components["schemas"]["PatientResponse"];
export type PatientPage = components["schemas"]["PatientListResponse"];

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

export function listPatients(
  cookieHeader: string,
  page: number,
  query: string,
  status: string | null = null,
): Promise<ApiResult<PatientPage>> {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (query !== "") params.set("q", query);
  if (status !== null && status !== "") params.set("status", status);
  const headers = cookieHeader === "" ? undefined : { cookie: cookieHeader };
  return getJson(`/patients?${params.toString()}`, patientPageData, headers);
}

export function getPatient(cookieHeader: string, patientId: string): Promise<ApiResult<Patient>> {
  const headers = cookieHeader === "" ? undefined : { cookie: cookieHeader };
  return getJson(`/patients/${encodeURIComponent(patientId)}`, patientData, headers);
}

export type ClinicianOption = { id: string; full_name: string };
export type AppointmentTypeOption = { id: string; name: string };
export type ClinicDayOption = { timezone: string };
export type UpcomingVisit = {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  clinician: { id: string; full_name: string };
  appointment_type: { id: string; name: string };
};

export function listClinicians(cookieHeader: string): Promise<ApiResult<ClinicianOption[]>> {
  return getJson("/clinicians", clinicianListData, cookieHeaders(cookieHeader));
}

export function listAppointmentTypes(cookieHeader: string): Promise<ApiResult<AppointmentTypeOption[]>> {
  return getJson("/appointment-types", appointmentTypeListData, cookieHeaders(cookieHeader));
}

export function getClinicDay(cookieHeader: string): Promise<ApiResult<ClinicDayOption>> {
  return getJson("/clinic/day", clinicDayData, cookieHeaders(cookieHeader));
}

export function listUpcomingAppointments(
  cookieHeader: string,
  patientId: string,
): Promise<ApiResult<UpcomingVisit[]>> {
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/appointments`,
    upcomingListData,
    cookieHeaders(cookieHeader),
  );
}

function cookieHeaders(cookieHeader: string): HeadersInit | undefined {
  if (cookieHeader === "") return undefined;
  return { cookie: cookieHeader };
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

function patientPageData(value: unknown): PatientPage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: Patient[] = [];
  for (const item of value.items) {
    const patient = patientData(item);
    if (patient === null) return null;
    items.push(patient);
  }
  return { items, page, page_size: pageSize, total };
}

function patientData(value: unknown): Patient | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const patientNumber = numberField(value, "patient_number");
  const displayId = stringField(value, "display_id");
  const fullName = stringField(value, "full_name");
  const phone = stringField(value, "phone");
  const createdAt = stringField(value, "created_at");
  const status = value.status;
  const dateOfBirth = value.date_of_birth;
  if (
    id === null ||
    patientNumber === null ||
    displayId === null ||
    fullName === null ||
    phone === null ||
    createdAt === null ||
    (status !== "active" && status !== "inactive") ||
    (dateOfBirth !== null && typeof dateOfBirth !== "string")
  ) {
    return null;
  }
  return {
    id,
    patient_number: patientNumber,
    display_id: displayId,
    full_name: fullName,
    phone,
    date_of_birth: dateOfBirth,
    status,
    created_at: createdAt,
  };
}

function clinicianListData(value: unknown): ClinicianOption[] | null {
  if (!Array.isArray(value)) return null;
  const rows: ClinicianOption[] = [];
  for (const item of value) {
    if (!isRecord(item)) return null;
    const id = stringField(item, "id");
    const fullName = stringField(item, "full_name");
    if (id === null || fullName === null) return null;
    rows.push({ id, full_name: fullName });
  }
  return rows;
}

function appointmentTypeListData(value: unknown): AppointmentTypeOption[] | null {
  if (!Array.isArray(value)) return null;
  const rows: AppointmentTypeOption[] = [];
  for (const item of value) {
    if (!isRecord(item)) return null;
    const id = stringField(item, "id");
    const name = stringField(item, "name");
    if (id === null || name === null) return null;
    rows.push({ id, name });
  }
  return rows;
}

function clinicDayData(value: unknown): ClinicDayOption | null {
  if (!isRecord(value)) return null;
  const timezone = stringField(value, "timezone");
  if (timezone === null || timezone === "") return null;
  return { timezone };
}

function upcomingListData(value: unknown): UpcomingVisit[] | null {
  if (!Array.isArray(value)) return null;
  const rows: UpcomingVisit[] = [];
  for (const item of value) {
    const visit = upcomingData(item);
    if (visit === null) return null;
    rows.push(visit);
  }
  return rows;
}

function upcomingData(value: unknown): UpcomingVisit | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const startsAt = stringField(value, "starts_at");
  const endsAt = stringField(value, "ends_at");
  const status = stringField(value, "status");
  const clinician = partyData(value.clinician);
  const appointmentType = typeNameData(value.appointment_type);
  if (id === null || startsAt === null || endsAt === null || status === null) return null;
  if (clinician === null || appointmentType === null) return null;
  return {
    id,
    starts_at: startsAt,
    ends_at: endsAt,
    status,
    clinician,
    appointment_type: appointmentType,
  };
}

function partyData(value: unknown): { id: string; full_name: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const fullName = stringField(value, "full_name");
  if (id === null || fullName === null) return null;
  return { id, full_name: fullName };
}

function typeNameData(value: unknown): { id: string; name: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  if (id === null || name === null) return null;
  return { id, name };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringField(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  if (typeof field !== "string") return null;
  return field;
}

function numberField(value: Record<string, unknown>, key: string): number | null {
  const field = value[key];
  if (typeof field !== "number" || !Number.isFinite(field)) return null;
  return field;
}

function stringListField(value: Record<string, unknown>, key: string): string[] | null {
  const field = value[key];
  if (!Array.isArray(field) || !field.every((item) => typeof item === "string")) return null;
  return field;
}
