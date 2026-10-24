import { readUploadContentType } from "@/features/documents/sizes";
import {
  genericApiError,
  isTimeoutError,
  NETWORK_ERROR_MESSAGE,
  parseErrorBody,
  TIMEOUT_ERROR_MESSAGE,
  UPLOAD_TIMEOUT_MS,
  type ApiError,
  type ApiResult,
} from "@/lib/api/errors";
import { fetchWithTimeout, readJson } from "@/lib/api/transport";
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
export type FollowUpTiming = "overdue" | "due_today" | "upcoming";
export type FollowUpQueueView = "due" | "all";
export type FollowUp = {
  id: string;
  patient_id: string;
  appointment_id: string | null;
  status: FollowUpStatus;
  due_on: string;
  created_at: string;
};
export type FollowUpQueueItem = {
  id: string;
  status: FollowUpStatus;
  due_on: string;
  timing: FollowUpTiming;
  patient: { id: string; display_id: string; full_name: string; phone: string };
};
export type FollowUpQueuePage = {
  items: FollowUpQueueItem[];
  total: number;
  page: number;
  page_size: number;
};

export type RecallStatus = "scheduled" | "contacted" | "booked";
export type RecallTiming = "overdue" | "due_today" | "upcoming";
export type RecallQueueView = "due" | "all";
export type RecallQueueItem = {
  id: string;
  status: RecallStatus;
  due_on: string;
  timing: RecallTiming;
  last_visit_on: string;
  recall_type: { id: string; name: string };
  patient: { id: string; display_id: string; full_name: string; phone: string };
};
export type RecallQueuePage = {
  items: RecallQueueItem[];
  total: number;
  page: number;
  page_size: number;
};

export function cancelFollowUp(followUpId: string): Promise<ApiResult<null>> {
  return sendEmpty("POST", `/api/follow-ups/${encodeURIComponent(followUpId)}/cancel`);
}

export function createFollowUp(patientId: string, dueOn: string): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/patients/${encodeURIComponent(patientId)}/follow-up`, { due_on: dueOn });
}

export type TimelineKind =
  | "patient_registered"
  | "visit_booked"
  | "visit_rescheduled"
  | "visit_cancelled"
  | "visit_arrived"
  | "visit_started"
  | "visit_completed"
  | "visit_no_show"
  | "care_item_added"
  | "care_item_started"
  | "care_item_completed"
  | "care_item_cancelled"
  | "care_session_recorded"
  | "follow_up_created"
  | "follow_up_updated"
  | "follow_up_contacted"
  | "follow_up_booked"
  | "follow_up_completed"
  | "follow_up_released"
  | "follow_up_cancelled"
  | "recall_created"
  | "recall_updated"
  | "recall_contacted"
  | "recall_booked"
  | "recall_completed"
  | "recall_released"
  | "recall_cancelled"
  | "document_uploaded"
  | "lab_work_created"
  | "lab_work_ready"
  | "lab_work_collected"
  | "lab_work_cancelled";

export type TimelineVisitSubject = {
  appointment_id: string;
  type_name: string;
  clinician_name: string;
  starts_at: string;
};

export type TimelineCareItemSubject = { name: string };

export type TimelineSessionSubject = { care_session_id: string; item_names: string[] };

export type TimelineFollowUpSubject = { due_on: string };

export type TimelineRecallSubject = { due_on: string; type_name: string };

export type TimelineDocumentSubject = { document_id: string; filename: string };

export type TimelineLabWorkSubject = { lab_work_id: string; title: string };

export type TimelineSubject =
  | TimelineVisitSubject
  | TimelineCareItemSubject
  | TimelineSessionSubject
  | TimelineFollowUpSubject
  | TimelineRecallSubject
  | TimelineDocumentSubject
  | TimelineLabWorkSubject
  | null;

export type TimelineItem = {
  id: string;
  kind: TimelineKind;
  occurred_at: string;
  actor: { id: string; name: string };
  subject: TimelineSubject;
};

export type TimelinePage = {
  items: TimelineItem[];
  total: number;
  page: number;
  page_size: number;
};

export type DocumentContentType = "application/pdf" | "image/png" | "image/jpeg";

export type DocumentAppointmentLink = {
  id: string;
  starts_at: string;
  type_name: string;
};

export type DocumentFollowUpLink = { id: string; due_on: string };

export type DocumentLabWorkLink = { id: string; title: string; status: LabWorkStatus };

export type DocumentItem = {
  id: string;
  filename: string;
  content_type: DocumentContentType;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by: { id: string; name: string };
  appointment: DocumentAppointmentLink | null;
  follow_up: DocumentFollowUpLink | null;
  lab_work: DocumentLabWorkLink | null;
};

export type DocumentPage = {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
};

const TIMELINE_KINDS: readonly TimelineKind[] = [
  "patient_registered",
  "visit_booked",
  "visit_rescheduled",
  "visit_cancelled",
  "visit_arrived",
  "visit_started",
  "visit_completed",
  "visit_no_show",
  "care_item_added",
  "care_item_started",
  "care_item_completed",
  "care_item_cancelled",
  "care_session_recorded",
  "follow_up_created",
  "follow_up_updated",
  "follow_up_contacted",
  "follow_up_booked",
  "follow_up_completed",
  "follow_up_released",
  "follow_up_cancelled",
  "recall_created",
  "recall_updated",
  "recall_contacted",
  "recall_booked",
  "recall_completed",
  "recall_released",
  "recall_cancelled",
  "document_uploaded",
  "lab_work_created",
  "lab_work_ready",
  "lab_work_collected",
  "lab_work_cancelled",
];

export function listTimeline(
  cookieHeader: string,
  patientId: string,
  page: number,
  pageSize = 20,
): Promise<ApiResult<TimelinePage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/timeline?${params.toString()}`,
    timelinePageData,
    cookieHeaders(cookieHeader),
  );
}

export type DocumentListFilter = {
  appointmentId?: string;
  followUpId?: string;
  labWorkId?: string;
};

export function listDocuments(
  cookieHeader: string,
  patientId: string,
  page: number,
  pageSize = 20,
  filter?: DocumentListFilter,
): Promise<ApiResult<DocumentPage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filter?.appointmentId) params.set("appointment_id", filter.appointmentId);
  if (filter?.followUpId) params.set("follow_up_id", filter.followUpId);
  if (filter?.labWorkId) params.set("lab_work_id", filter.labWorkId);
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/documents?${params.toString()}`,
    documentPageData,
    cookieHeaders(cookieHeader),
  );
}

/** The browser list goes through the `/api` rewrite so the session cookie is sent. */
export function listDocumentsInBrowser(
  patientId: string,
  page: number,
  pageSize = 20,
): Promise<ApiResult<DocumentPage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return getJsonFromBrowser(
    `/api/patients/${encodeURIComponent(patientId)}/documents?${params.toString()}`,
    documentPageData,
  );
}

export function getDocument(
  cookieHeader: string,
  patientId: string,
  documentId: string,
): Promise<ApiResult<DocumentItem>> {
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}`,
    documentItemData,
    cookieHeaders(cookieHeader),
  );
}

/** Sends the file as the raw request body. The name goes in a header so URLs stay out of logs. */
export async function uploadDocument(
  patientId: string,
  file: File,
  filter?: DocumentListFilter,
): Promise<ApiResult<null>> {
  const contentType = await readUploadContentType(file);
  if (contentType === null) {
    return {
      ok: false,
      error: {
        kind: "api",
        status: 422,
        code: "validation_error",
        message: "That file type is not allowed.",
        requestId: "",
      },
    };
  }
  const params = new URLSearchParams();
  if (filter?.appointmentId) params.set("appointment_id", filter.appointmentId);
  if (filter?.followUpId) params.set("follow_up_id", filter.followUpId);
  if (filter?.labWorkId) params.set("lab_work_id", filter.labWorkId);
  const query = params.toString() === "" ? "" : `?${params.toString()}`;
  return sendRequest(
    `/api/patients/${encodeURIComponent(patientId)}/documents${query}`,
    {
      method: "POST",
      headers: {
        "content-type": contentType,
        "x-document-filename": encodeURIComponent(file.name),
      },
      body: file,
    },
    UPLOAD_TIMEOUT_MS,
  );
}

export type LabWorkStatus = "pending" | "ready" | "collected" | "cancelled";

export type LabWorkListView = "open" | "all";

export type LabWorkItem = {
  id: string;
  status: LabWorkStatus;
  title: string;
  expected_on: string | null;
  overdue: boolean;
  appointment: DocumentAppointmentLink | null;
  patient: { id: string; display_id: string; full_name: string; phone: string };
  created_at: string;
  created_by: { id: string; name: string };
};

export type LabWorkPage = {
  items: LabWorkItem[];
  total: number;
  page: number;
  page_size: number;
};

export function getLabWork(
  cookieHeader: string,
  labWorkId: string,
): Promise<ApiResult<LabWorkItem>> {
  return getJson(
    `/lab-work/${encodeURIComponent(labWorkId)}`,
    labWorkItemData,
    cookieHeaders(cookieHeader),
  );
}

export function listPatientLabWork(
  cookieHeader: string,
  patientId: string,
  page: number,
  pageSize = 20,
): Promise<ApiResult<LabWorkPage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return getJson(
    `/patients/${encodeURIComponent(patientId)}/lab-work?${params.toString()}`,
    labWorkPageData,
    cookieHeaders(cookieHeader),
  );
}

export function listClinicLabWork(
  cookieHeader: string,
  view: LabWorkListView,
  page: number,
  pageSize = 20,
): Promise<ApiResult<LabWorkPage>> {
  const params = new URLSearchParams({
    view,
    page: String(page),
    page_size: String(pageSize),
  });
  return getJson(`/lab-work?${params.toString()}`, labWorkPageData, cookieHeaders(cookieHeader));
}

export type InventoryCategory = { id: string; name: string; item_count: number };
export type InventoryItemStatus = "active" | "inactive";
export type InventoryListStatus = "active" | "inactive" | "all";
export type InventoryItem = {
  id: string;
  name: string;
  category: { id: string; name: string };
  unit: string;
  low_stock_threshold: number;
  status: InventoryItemStatus;
  batch_count: number;
};
export type InventoryBatch = {
  id: string;
  batch_number: string;
  expiry_on: string | null;
  expired: boolean;
  created_at: string;
};
export type InventoryItemDetail = InventoryItem & { batches: InventoryBatch[] };
export type InventoryItemPage = {
  items: InventoryItem[];
  total: number;
  page: number;
  page_size: number;
};

export function listInventoryCategories(
  cookieHeader: string,
): Promise<ApiResult<InventoryCategory[]>> {
  return getJson("/inventory/categories", inventoryCategoryListData, cookieHeaders(cookieHeader));
}

export function listInventoryItems(
  cookieHeader: string,
  status: InventoryListStatus,
  categoryId: string,
  query: string,
  page: number,
): Promise<ApiResult<InventoryItemPage>> {
  const params = new URLSearchParams({
    status,
    page: String(page),
    page_size: "20",
  });
  if (categoryId !== "") params.set("category_id", categoryId);
  if (query !== "") params.set("q", query);
  return getJson(
    `/inventory/items?${params.toString()}`,
    inventoryItemPageData,
    cookieHeaders(cookieHeader),
  );
}

export function getInventoryItem(
  cookieHeader: string,
  itemId: string,
): Promise<ApiResult<InventoryItemDetail>> {
  return getJson(
    `/inventory/items/${encodeURIComponent(itemId)}`,
    inventoryItemDetailData,
    cookieHeaders(cookieHeader),
  );
}

export function createInventoryCategory(name: string): Promise<ApiResult<null>> {
  return sendJson("POST", "/api/inventory/categories", { name });
}

export function renameInventoryCategory(categoryId: string, name: string): Promise<ApiResult<null>> {
  return sendJson("PATCH", `/api/inventory/categories/${encodeURIComponent(categoryId)}`, { name });
}

export function createInventoryItem(input: {
  name: string;
  categoryId: string;
  unit: string;
  lowStockThreshold: string;
}): Promise<ApiResult<null>> {
  const threshold = Number(input.lowStockThreshold);
  return sendJson("POST", "/api/inventory/items", {
    name: input.name,
    category_id: input.categoryId,
    unit: input.unit,
    low_stock_threshold: Number.isInteger(threshold) ? threshold : input.lowStockThreshold,
  });
}

export function updateInventoryItem(
  itemId: string,
  input: { name: string; categoryId: string; unit: string; lowStockThreshold: string },
): Promise<ApiResult<null>> {
  const threshold = Number(input.lowStockThreshold);
  return sendJson("PATCH", `/api/inventory/items/${encodeURIComponent(itemId)}`, {
    name: input.name,
    category_id: input.categoryId,
    unit: input.unit,
    low_stock_threshold: Number.isInteger(threshold) ? threshold : input.lowStockThreshold,
  });
}

export function setInventoryItemStatus(
  itemId: string,
  status: InventoryItemStatus,
): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/inventory/items/${encodeURIComponent(itemId)}/status`, { status });
}

export function createInventoryBatch(
  itemId: string,
  batchNumber: string,
  expiryOn: string,
): Promise<ApiResult<null>> {
  const body: { batch_number: string; expiry_on?: string } = { batch_number: batchNumber };
  if (expiryOn !== "") body.expiry_on = expiryOn;
  return sendJson("POST", `/api/inventory/items/${encodeURIComponent(itemId)}/batches`, body);
}

export function updateInventoryBatch(
  batchId: string,
  batchNumber: string,
  expiryOn: string,
): Promise<ApiResult<null>> {
  return sendJson("PATCH", `/api/inventory/batches/${encodeURIComponent(batchId)}`, {
    batch_number: batchNumber,
    expiry_on: expiryOn === "" ? null : expiryOn,
  });
}

export function createLabWork(
  patientId: string,
  title: string,
  expectedOn: string,
): Promise<ApiResult<null>> {
  const body: { title: string; expected_on?: string } = { title };
  if (expectedOn !== "") body.expected_on = expectedOn;
  return sendJson("POST", `/api/patients/${encodeURIComponent(patientId)}/lab-work`, body);
}

export function changeLabWorkStatus(
  labWorkId: string,
  status: "ready" | "collected" | "cancelled",
): Promise<ApiResult<null>> {
  return sendJson("POST", `/api/lab-work/${encodeURIComponent(labWorkId)}/status`, { status });
}

export function updateDocumentLinks(
  patientId: string,
  documentId: string,
  body: {
    appointment_id?: string | null;
    follow_up_id?: string | null;
    lab_work_id?: string | null;
  },
): Promise<ApiResult<null>> {
  return sendJson(
    "PATCH",
    `/api/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}`,
    body,
  );
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

export function listFollowUps(
  cookieHeader: string,
  page: number,
  view: FollowUpQueueView = "due",
  pageSize = 20,
): Promise<ApiResult<FollowUpQueuePage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    view,
  });
  return getJson(`/follow-ups?${params.toString()}`, followUpQueuePageData, cookieHeaders(cookieHeader));
}

export function cancelRecall(recallId: string): Promise<ApiResult<null>> {
  return sendEmpty("POST", `/api/recalls/${encodeURIComponent(recallId)}/cancel`);
}

export function markRecallContacted(recallId: string): Promise<ApiResult<null>> {
  return sendEmpty("POST", `/api/recalls/${encodeURIComponent(recallId)}/contacted`);
}

export function getRecall(
  cookieHeader: string,
  recallId: string,
): Promise<ApiResult<RecallQueueItem>> {
  return getJson(
    `/recalls/${encodeURIComponent(recallId)}`,
    recallQueueItemData,
    cookieHeaders(cookieHeader),
  );
}

export function listRecalls(
  cookieHeader: string,
  page: number,
  view: RecallQueueView = "due",
  pageSize = 20,
): Promise<ApiResult<RecallQueuePage>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    view,
  });
  return getJson(`/recalls?${params.toString()}`, recallQueuePageData, cookieHeaders(cookieHeader));
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

async function getJsonFromBrowser<T>(
  path: string,
  parse: (value: unknown) => T | null,
): Promise<ApiResult<T>> {
  try {
    const response = await fetchWithTimeout(path, { credentials: "same-origin" });
    if (!response.ok) {
      return { ok: false, error: parseErrorBody(response.status, await readJson(response)) };
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

async function getJson<T>(
  path: string,
  parse: (value: unknown) => T | null,
  headers?: HeadersInit,
): Promise<ApiResult<T>> {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl()}${path}`, {
      cache: "no-store",
      headers,
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

function sendEmpty(method: "POST", path: string): Promise<ApiResult<null>> {
  return sendRequest(path, { method });
}

function sendJson(
  method: "POST" | "PATCH",
  path: string,
  body: unknown,
): Promise<ApiResult<null>> {
  return sendRequest(path, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function sendRequest(
  path: string,
  init: RequestInit,
  timeoutMs?: number,
): Promise<ApiResult<null>> {
  try {
    const response = await fetchWithTimeout(
      path,
      { ...init, credentials: "same-origin" },
      undefined,
      timeoutMs,
    );
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

function timelinePageData(value: unknown): TimelinePage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: TimelineItem[] = [];
  for (const item of value.items) {
    const row = timelineItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function timelineItemData(value: unknown): TimelineItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const occurredAt = stringField(value, "occurred_at");
  const kind = value.kind;
  if (id === null || occurredAt === null || !isTimelineKind(kind)) return null;
  const actor = timelineActorData(value.actor);
  const subject = timelineSubjectData(kind, value.subject);
  if (actor === null || subject === undefined) return null;
  return { id, kind, occurred_at: occurredAt, actor, subject };
}

function isTimelineKind(value: unknown): value is TimelineKind {
  return typeof value === "string" && TIMELINE_KINDS.some((kind) => kind === value);
}

function timelineActorData(value: unknown): { id: string; name: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  if (id === null || name === null) return null;
  return { id, name };
}

function timelineSubjectData(kind: TimelineKind, value: unknown): TimelineSubject | undefined {
  if (kind === "patient_registered") return value === null ? null : undefined;
  if (kind.startsWith("visit_")) return visitSubjectData(value);
  if (kind.startsWith("care_item_")) return careItemSubjectData(value);
  if (kind === "care_session_recorded") return sessionSubjectData(value);
  if (kind.startsWith("follow_up_")) return followUpSubjectData(value);
  if (kind.startsWith("recall_")) return recallSubjectData(value);
  if (kind === "document_uploaded") return documentSubjectData(value);
  if (kind.startsWith("lab_work_")) return labWorkSubjectData(value);
  return undefined;
}

function labWorkSubjectData(value: unknown): TimelineLabWorkSubject | undefined {
  if (!isRecord(value)) return undefined;
  const labWorkId = stringField(value, "lab_work_id");
  const title = stringField(value, "title");
  if (labWorkId === null || title === null) return undefined;
  return { lab_work_id: labWorkId, title };
}

function documentSubjectData(value: unknown): TimelineDocumentSubject | undefined {
  if (!isRecord(value)) return undefined;
  const documentId = stringField(value, "document_id");
  const filename = stringField(value, "filename");
  if (documentId === null || filename === null) return undefined;
  return { document_id: documentId, filename };
}

function visitSubjectData(value: unknown): TimelineVisitSubject | undefined {
  if (!isRecord(value)) return undefined;
  const appointmentId = stringField(value, "appointment_id");
  const typeName = stringField(value, "type_name");
  const clinicianName = stringField(value, "clinician_name");
  const startsAt = stringField(value, "starts_at");
  if (appointmentId === null || typeName === null || clinicianName === null || startsAt === null) {
    return undefined;
  }
  return {
    appointment_id: appointmentId,
    type_name: typeName,
    clinician_name: clinicianName,
    starts_at: startsAt,
  };
}

function careItemSubjectData(value: unknown): TimelineCareItemSubject | undefined {
  if (!isRecord(value)) return undefined;
  const name = stringField(value, "name");
  if (name === null || "care_session_id" in value) return undefined;
  return { name };
}

function sessionSubjectData(value: unknown): TimelineSessionSubject | undefined {
  if (!isRecord(value) || !Array.isArray(value.item_names)) return undefined;
  const careSessionId = stringField(value, "care_session_id");
  if (careSessionId === null || !value.item_names.every((name) => typeof name === "string")) {
    return undefined;
  }
  return { care_session_id: careSessionId, item_names: value.item_names };
}

function followUpSubjectData(value: unknown): TimelineFollowUpSubject | undefined {
  if (!isRecord(value) || "type_name" in value) return undefined;
  const dueOn = stringField(value, "due_on");
  if (dueOn === null) return undefined;
  return { due_on: dueOn };
}

function recallSubjectData(value: unknown): TimelineRecallSubject | undefined {
  if (!isRecord(value)) return undefined;
  const dueOn = stringField(value, "due_on");
  const typeName = stringField(value, "type_name");
  if (dueOn === null || typeName === null) return undefined;
  return { due_on: dueOn, type_name: typeName };
}

function documentPageData(value: unknown): DocumentPage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: DocumentItem[] = [];
  for (const item of value.items) {
    const row = documentItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function documentItemData(value: unknown): DocumentItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const filename = stringField(value, "filename");
  const sizeBytes = numberField(value, "size_bytes");
  const uploadedAt = stringField(value, "uploaded_at");
  const contentType = value.content_type;
  if (id === null || filename === null || sizeBytes === null || uploadedAt === null) return null;
  if (!isDocumentContentType(contentType)) return null;
  const uploadedBy = timelineActorData(value.uploaded_by);
  const appointment = documentAppointmentData(value.appointment);
  const followUp = documentFollowUpData(value.follow_up);
  const labWork = documentLabWorkData(value.lab_work);
  if (
    uploadedBy === null ||
    appointment === undefined ||
    followUp === undefined ||
    labWork === undefined
  ) {
    return null;
  }
  return {
    id,
    filename,
    content_type: contentType,
    size_bytes: sizeBytes,
    uploaded_at: uploadedAt,
    uploaded_by: uploadedBy,
    appointment,
    follow_up: followUp,
    lab_work: labWork,
  };
}

function isLabWorkStatus(value: unknown): value is LabWorkStatus {
  return value === "pending" || value === "ready" || value === "collected" || value === "cancelled";
}

function labWorkPageData(value: unknown): LabWorkPage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: LabWorkItem[] = [];
  for (const item of value.items) {
    const row = labWorkItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function labWorkItemData(value: unknown): LabWorkItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const title = stringField(value, "title");
  const createdAt = stringField(value, "created_at");
  const status = value.status;
  if (id === null || title === null || createdAt === null || !isLabWorkStatus(status)) return null;
  if (typeof value.overdue !== "boolean") return null;
  const expectedOn = value.expected_on;
  if (expectedOn !== null && typeof expectedOn !== "string") return null;
  const appointment = documentAppointmentData(value.appointment);
  const patient = labPatientData(value.patient);
  const createdBy = timelineActorData(value.created_by);
  if (appointment === undefined || patient === null || createdBy === null) return null;
  return {
    id,
    status,
    title,
    expected_on: expectedOn,
    overdue: value.overdue,
    appointment,
    patient,
    created_at: createdAt,
    created_by: createdBy,
  };
}

function labPatientData(
  value: unknown,
): { id: string; display_id: string; full_name: string; phone: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const displayId = stringField(value, "display_id");
  const fullName = stringField(value, "full_name");
  const phone = stringField(value, "phone");
  if (id === null || displayId === null || fullName === null || phone === null) return null;
  return { id, display_id: displayId, full_name: fullName, phone };
}

function documentLabWorkData(value: unknown): DocumentLabWorkLink | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const id = stringField(value, "id");
  const title = stringField(value, "title");
  const status = value.status;
  if (id === null || title === null || !isLabWorkStatus(status)) return undefined;
  return { id, title, status };
}

function documentAppointmentData(value: unknown): DocumentAppointmentLink | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const id = stringField(value, "id");
  const startsAt = stringField(value, "starts_at");
  const typeName = stringField(value, "type_name");
  if (id === null || startsAt === null || typeName === null) return undefined;
  return { id, starts_at: startsAt, type_name: typeName };
}

function documentFollowUpData(value: unknown): DocumentFollowUpLink | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const id = stringField(value, "id");
  const dueOn = stringField(value, "due_on");
  if (id === null || dueOn === null) return undefined;
  return { id, due_on: dueOn };
}

function isDocumentContentType(value: unknown): value is DocumentContentType {
  return value === "application/pdf" || value === "image/png" || value === "image/jpeg";
}

function followUpEnvelope(value: unknown): { follow_up: FollowUp | null } | null {
  if (!isRecord(value) || !("follow_up" in value)) return null;
  if (value.follow_up === null) return { follow_up: null };
  const followUp = followUpData(value.follow_up);
  if (followUp === null) return null;
  return { follow_up: followUp };
}

function followUpQueuePageData(value: unknown): FollowUpQueuePage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: FollowUpQueueItem[] = [];
  for (const item of value.items) {
    const row = followUpQueueItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function followUpQueueItemData(value: unknown): FollowUpQueueItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const dueOn = stringField(value, "due_on");
  const status = value.status;
  const timing = value.timing;
  const patient = followUpQueuePatientData(value.patient);
  if (id === null || dueOn === null || patient === null) return null;
  if (status !== "scheduled" && status !== "contacted" && status !== "booked") return null;
  if (timing !== "overdue" && timing !== "due_today" && timing !== "upcoming") return null;
  return { id, status, due_on: dueOn, timing, patient };
}

function recallQueuePageData(value: unknown): RecallQueuePage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: RecallQueueItem[] = [];
  for (const item of value.items) {
    const row = recallQueueItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function recallQueueItemData(value: unknown): RecallQueueItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const dueOn = stringField(value, "due_on");
  const lastVisitOn = stringField(value, "last_visit_on");
  const status = value.status;
  const timing = value.timing;
  const recallType = recallTypeData(value.recall_type);
  const patient = followUpQueuePatientData(value.patient);
  if (id === null || dueOn === null || lastVisitOn === null || recallType === null || patient === null) {
    return null;
  }
  if (status !== "scheduled" && status !== "contacted" && status !== "booked") return null;
  if (timing !== "overdue" && timing !== "due_today" && timing !== "upcoming") return null;
  return {
    id,
    status,
    due_on: dueOn,
    timing,
    last_visit_on: lastVisitOn,
    recall_type: recallType,
    patient,
  };
}

function recallTypeData(value: unknown): { id: string; name: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  if (id === null || name === null) return null;
  return { id, name };
}

function followUpQueuePatientData(
  value: unknown,
): { id: string; display_id: string; full_name: string; phone: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const displayId = stringField(value, "display_id");
  const fullName = stringField(value, "full_name");
  const phone = stringField(value, "phone");
  if (id === null || displayId === null || fullName === null || phone === null) return null;
  return { id, display_id: displayId, full_name: fullName, phone };
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

function inventoryCategoryListData(value: unknown): InventoryCategory[] | null {
  if (!Array.isArray(value)) return null;
  const categories: InventoryCategory[] = [];
  for (const item of value) {
    const category = inventoryCategoryData(item);
    if (category === null) return null;
    categories.push(category);
  }
  return categories;
}

function inventoryCategoryData(value: unknown): InventoryCategory | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  const itemCount = numberField(value, "item_count");
  if (id === null || name === null || itemCount === null) return null;
  return { id, name, item_count: itemCount };
}

function inventoryItemPageData(value: unknown): InventoryItemPage | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const page = numberField(value, "page");
  const pageSize = numberField(value, "page_size");
  const total = numberField(value, "total");
  if (page === null || pageSize === null || total === null) return null;
  const items: InventoryItem[] = [];
  for (const item of value.items) {
    const row = inventoryItemData(item);
    if (row === null) return null;
    items.push(row);
  }
  return { items, page, page_size: pageSize, total };
}

function inventoryItemDetailData(value: unknown): InventoryItemDetail | null {
  const item = inventoryItemData(value);
  if (item === null || !isRecord(value) || !Array.isArray(value.batches)) return null;
  const batches: InventoryBatch[] = [];
  for (const batch of value.batches) {
    const row = inventoryBatchData(batch);
    if (row === null) return null;
    batches.push(row);
  }
  return { ...item, batches };
}

function inventoryItemData(value: unknown): InventoryItem | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  const unit = stringField(value, "unit");
  const threshold = numberField(value, "low_stock_threshold");
  const batchCount = numberField(value, "batch_count");
  const status = value.status;
  const category = inventoryCategoryLinkData(value.category);
  if (id === null || name === null || unit === null || threshold === null || batchCount === null) {
    return null;
  }
  if (category === null || (status !== "active" && status !== "inactive")) return null;
  return {
    id,
    name,
    category,
    unit,
    low_stock_threshold: threshold,
    status,
    batch_count: batchCount,
  };
}

function inventoryCategoryLinkData(value: unknown): { id: string; name: string } | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const name = stringField(value, "name");
  if (id === null || name === null) return null;
  return { id, name };
}

function inventoryBatchData(value: unknown): InventoryBatch | null {
  if (!isRecord(value)) return null;
  const id = stringField(value, "id");
  const batchNumber = stringField(value, "batch_number");
  const createdAt = stringField(value, "created_at");
  const expiry = value.expiry_on;
  if (id === null || batchNumber === null || createdAt === null) return null;
  if (expiry !== null && typeof expiry !== "string") return null;
  if (typeof value.expired !== "boolean") return null;
  return {
    id,
    batch_number: batchNumber,
    expiry_on: expiry,
    expired: value.expired,
    created_at: createdAt,
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
