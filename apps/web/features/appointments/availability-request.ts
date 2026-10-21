import type { components } from "@/lib/api/schema";
import { fetchWithTimeout, readJson } from "@/lib/api/transport";
import { wallTime } from "@/features/appointments/wall-time";

export type AvailabilityInput =
  | { date: string; clinicianId: string; appointmentTypeId: string }
  | { date: string; clinicianId: string; rescheduleAppointmentId: string };

export type SlotChoice = { startsAt: string; label: string };

export type AvailabilityResult =
  | { kind: "loaded"; isOpen: boolean; slots: SlotChoice[] }
  | { kind: "forbidden" }
  | { kind: "error" }
  | { kind: "aborted" };

type AvailabilityProjection = Pick<components["schemas"]["AvailabilityResponse"], "is_open" | "slots">;

/** Loads and validates one booking or rescheduling availability response. */
export async function loadAvailability(
  input: AvailabilityInput,
  cancellation: AbortSignal,
): Promise<AvailabilityResult> {
  try {
    const response = await fetchWithTimeout(
      `/api/appointments/availability?${availabilityParams(input).toString()}`,
      { credentials: "same-origin" },
      cancellation,
    );
    if (cancellation.aborted) return { kind: "aborted" };
    if (response.status === 403) return { kind: "forbidden" };
    if (!response.ok) return { kind: "error" };
    const parsed = parseAvailability(await readJson(response));
    if (cancellation.aborted) return { kind: "aborted" };
    return parsed === null ? { kind: "error" } : { kind: "loaded", ...parsed };
  } catch {
    return cancellation.aborted ? { kind: "aborted" } : { kind: "error" };
  }
}

function availabilityParams(input: AvailabilityInput): URLSearchParams {
  const params = new URLSearchParams({ date: input.date, clinician_id: input.clinicianId });
  if ("appointmentTypeId" in input) params.set("appointment_type_id", input.appointmentTypeId);
  else params.set("reschedule_appointment_id", input.rescheduleAppointmentId);
  return params;
}

function parseAvailability(value: unknown): { isOpen: boolean; slots: SlotChoice[] } | null {
  if (!isAvailabilityProjection(value)) return null;
  const slots: SlotChoice[] = [];
  for (const slot of value.slots) {
    const label = wallTime(slot.starts_at);
    if (label === null) return null;
    slots.push({ startsAt: slot.starts_at, label });
  }
  return { isOpen: value.is_open, slots };
}

function isAvailabilityProjection(value: unknown): value is AvailabilityProjection {
  if (typeof value !== "object" || value === null || !("is_open" in value) || !("slots" in value)) {
    return false;
  }
  if (typeof value.is_open !== "boolean" || !Array.isArray(value.slots)) return false;
  return value.slots.every(
    (slot) => typeof slot === "object" && slot !== null && "starts_at" in slot && typeof slot.starts_at === "string",
  );
}
