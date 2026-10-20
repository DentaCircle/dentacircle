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

export type CalendarVisit = {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  patient: { id: string; full_name: string; display_id: string };
  clinician: { id: string; full_name: string };
  appointment_type: { id: string; name: string };
};

export function getAppointment(
  cookieHeader: string,
  appointmentId: string,
): Promise<ApiResult<CalendarVisit>> {
  return getJson(
    `/appointments/${encodeURIComponent(appointmentId)}`,
    calendarVisitData,
    cookieHeaders(cookieHeader),
  );
}

export function listAppointments(
  cookieHeader: string,
  rangeFrom: string,
  rangeTo: string,
  clinicianId: string | null,
): Promise<ApiResult<CalendarVisit[]>> {
  const params = new URLSearchParams({ from: rangeFrom, to: rangeTo });
  if (clinicianId !== null && clinicianId !== "") params.set("clinician_id", clinicianId);
  return getJson(`/appointments?${params.toString()}`, calendarListData, cookieHeaders(cookieHeader));
}

export type AppointmentStatusTarget = "arrived" | "in_progress" | "completed" | "no_show";

export function changeAppointmentStatus(
  appointmentId: string,
  status: AppointmentStatusTarget,
  followUpDueOn?: string,
): Promise<ApiResult<null>> {
  const body: { status: AppointmentStatusTarget; follow_up_due_on?: string } = { status };
  if (followUpDueOn !== undefined && followUpDueOn !== "") body.follow_up_due_on = followUpDueOn;
  return sendJson("POST", `/api/appointments/${encodeURIComponent(appointmentId)}/status`, body);
}

export type CareItemStatus = "planned" | "started" | "completed" | "cancelled";
export type CareStatusTarget = "started" | "completed" | "cancelled";
export type CareItem = {
  id: string;
  name: string;
  status: CareItemStatus;
  created_at: string;
};
export type CarePlan = {
  id: string;
  patient_id: string;
  title: string;
  created_at: string;
  is_open: boolean;
  items: CareItem[];
};

export type FollowUpStatus = "scheduled" | "contacted" | "booked";
export type FollowUp = {
  id: string;
  patient_id: string;
  appointment_id: string | null;
  status: FollowUpStatus;
  due_on: string;
  created_at: string;
};

export function createFollowUp(patientId: string, dueOn: string): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/patients/${encodeURIComponent(patientId)}/follow-up`, { due_on: dueOn });
}

export function getFollowUp(
  cookieHeader: string,
  patientId: string,
): Promise<ApiResult<{ follow_up: FollowUp | null }>> {
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/follow-up`,
    followUpEnvelope,
    cookieHeaders(cookieHeader),
  );
}

export function listCarePlans(cookieHeader: string, patientId: string): Promise<ApiResult<CarePlan[]>> {
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/care-plans`,
    carePlanListData,
    cookieHeaders(cookieHeader),
  );
}

export function createCarePlan(patientId: string, title: string): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/patients/${encodeURIComponent(patientId)}/care-plans`, { title });
}

export function addCareItem(planId: string, name: string): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/care-plans/${encodeURIComponent(planId)}/items`, { name });
}

export function renameCareItem(itemId: string, name: string): Promise<ApiResult<null>> {
  return sendJson("PATCH", `/api/care-items/${encodeURIComponent(itemId)}`, { name });
}

export function changeCareItemStatus(itemId: string, status: CareStatusTarget): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/care-items/${encodeURIComponent(itemId)}/status`, { status });
}

export type CareSessionResult = "started" | "completed";
export type CareSessionItem = {
  care_item_id: string;
  name: string;
  plan_title: string;
  status: CareSessionResult;
};
export type CareSession = {
  id: string;
  appointment_id: string;
  patient_id: string;
  recorded_by_name: string;
  created_at: string;
  items: CareSessionItem[];
};

export function getCareSession(
  cookieHeader: string,
  appointmentId: string,
): Promise<ApiResult<{ session: CareSession | null }>> {
  return getJson(
    `/appointments/${encodeURIComponent(appointmentId)}/care-session`,
    careSessionEnvelope,
    cookieHeaders(cookieHeader),
  );
}

export function recordCareSession(
  appointmentId: string,
  items: { care_item_id: string; status: CareSessionResult }[],
): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/appointments/${encodeURIComponent(appointmentId)}/care-session`, {
    items,
  });
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

async function sendJson(method: "POST" | "PATCH", path: string, body: unknown): Promise<ApiResult<null>> {
  try {
    const response = await fetch(path, {
      method,
      headers: { "content-type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { ok: false, error: parseErrorBody(response.status, await readJson(response)) };
    }
    return { ok: true, data: null };
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

function calendarListData(value: unknown): CalendarVisit[] | null {
  if (!Array.isArray(value)) return null;
  const rows: CalendarVisit[] = [];
  for (const item of value) {
    const visit = calendarVisitData(item);
    if (visit === null) return null;
    rows.push(visit);
  }
  return rows;
}

function calendarVisitData(value: unknown): CalendarVisit | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const startsAt = stringField(value, "starts_at");
  const endsAt = stringField(value, "ends_at");
  const status = stringField(value, "status");
  const patient = patientSummaryData(value.patient);
  const clinician = partyData(value.clinician);
  const appointmentType = typeNameData(value.appointment_type);
  if (id === null || startsAt === null || endsAt === null || status === null) return null;
  if (patient === null || clinician === null || appointmentType === null) return null;
  return {
    id,
    starts_at: startsAt,
    ends_at: endsAt,
    status,
    patient,
    clinician,
    appointment_type: appointmentType,
  };
}

function patientSummaryData(
  value: unknown,
): { id: string; full_name: string; display_id: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const fullName = stringField(value, "full_name");
  const displayId = stringField(value, "display_id");
  if (id === null || fullName === null || displayId === null) return null;
  return { id, full_name: fullName, display_id: displayId };
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

function careSessionEnvelope(value: unknown): { session: CareSession | null } | null {
  if (!isRecord(value) || !("session" in value)) return null;
  if (value.session === null) return { session: null };
  const session = careSessionData(value.session);
  if (session === null) return null;
  return { session };
}

function careSessionData(value: unknown): CareSession | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const appointmentId = stringField(value, "appointment_id");
  const patientId = stringField(value, "patient_id");
  const recordedByName = stringField(value, "recorded_by_name");
  const createdAt = stringField(value, "created_at");
  if (!Array.isArray(value.items)) return null;
  if (
    id === null ||
    appointmentId === null ||
    patientId === null ||
    recordedByName === null ||
    createdAt === null
  ) {
    return null;
  }
  const items: CareSessionItem[] = [];
  for (const item of value.items) {
    const line = careSessionItemData(item);
    if (line === null) return null;
    items.push(line);
  }
  return {
    id,
    appointment_id: appointmentId,
    patient_id: patientId,
    recorded_by_name: recordedByName,
    created_at: createdAt,
    items,
  };
}

function careSessionItemData(value: unknown): CareSessionItem | null {
  if (!isRecord(value)) return null;
  const careItemId = stringField(value, "care_item_id");
  const name = stringField(value, "name");
  const planTitle = stringField(value, "plan_title");
  const status = stringField(value, "status");
  if (careItemId === null || name === null || planTitle === null) return null;
  if (status !== "started" && status !== "completed") return null;
  return { care_item_id: careItemId, name, plan_title: planTitle, status };
}

function followUpEnvelope(value: unknown): { follow_up: FollowUp | null } | null {
  if (!isRecord(value) || !("follow_up" in value)) return null;
  if (value.follow_up === null) return { follow_up: null };
  const followUp = followUpData(value.follow_up);
  if (followUp === null) return null;
  return { follow_up: followUp };
}

function followUpData(value: unknown): FollowUp | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const patientId = stringField(value, "patient_id");
  const dueOn = stringField(value, "due_on");
  const createdAt = stringField(value, "created_at");
  const status = value.status;
  const appointmentId = value.appointment_id;
  if (appointmentId !== null && typeof appointmentId !== "string") return null;
  if (id === null || patientId === null || dueOn === null || createdAt === null) return null;
  if (status !== "scheduled" && status !== "contacted" && status !== "booked") return null;
  return {
    id,
    patient_id: patientId,
    appointment_id: appointmentId,
    status,
    due_on: dueOn,
    created_at: createdAt,
  };
}

function carePlanListData(value: unknown): CarePlan[] | null {
  if (!Array.isArray(value)) return null;
  const plans: CarePlan[] = [];
  for (const item of value) {
    const plan = carePlanData(item);
    if (plan === null) return null;
    plans.push(plan);
  }
  return plans;
}

function carePlanData(value: unknown): CarePlan | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const id = stringField(value, "id");
  const patientId = stringField(value, "patient_id");
  const title = stringField(value, "title");
  const createdAt = stringField(value, "created_at");
  if (id === null || patientId === null || title === null || createdAt === null) return null;
  if (typeof value.is_open !== "boolean") return null;
  const items: CareItem[] = [];
  for (const entry of value.items) {
    const item = careItemData(entry);
    if (item === null) return null;
    items.push(item);
  }
  return { id, patient_id: patientId, title, created_at: createdAt, is_open: value.is_open, items };
}

function careItemData(value: unknown): CareItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  const createdAt = stringField(value, "created_at");
  const status = value.status;
  if (id === null || name === null || createdAt === null) return null;
  if (status !== "planned" && status !== "started" && status !== "completed" && status !== "cancelled") {
    return null;
  }
  return { id, name, status, created_at: createdAt };
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
