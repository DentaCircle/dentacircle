import { useEffect, useMemo, useRef, useState } from "react";

import {
  loadAvailability,
  type AvailabilityInput,
  type SlotChoice,
} from "@/features/appointments/availability-request";
import type { TimesState } from "@/features/appointments/time-slots";

type SelectedSlot = { key: string; startsAt: string } | null;

/** Shares availability loading while ensuring only the newest request can update a form. */
export function useAvailability(input: AvailabilityInput) {
  const appointmentTypeId = "appointmentTypeId" in input ? input.appointmentTypeId : null;
  const rescheduleAppointmentId =
    "rescheduleAppointmentId" in input ? input.rescheduleAppointmentId : null;
  const requestInput = useMemo<AvailabilityInput>(() => {
    if (appointmentTypeId !== null) {
      return { date: input.date, clinicianId: input.clinicianId, appointmentTypeId };
    }
    return { date: input.date, clinicianId: input.clinicianId, rescheduleAppointmentId: rescheduleAppointmentId ?? "" };
  }, [appointmentTypeId, input.clinicianId, input.date, rescheduleAppointmentId]);
  const [slots, setSlots] = useState<SlotChoice[]>([]);
  const [timesState, setTimesState] = useState<TimesState>("loading");
  const [selectedSlot, setSelectedSlot] = useState<SelectedSlot>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestNumber = useRef(0);
  const key = availabilityKey(requestInput);
  const selected = selectedSlot?.key === key ? selectedSlot.startsAt : null;

  useEffect(() => {
    const controller = new AbortController();
    const thisRequest = ++requestNumber.current;
    setTimesState("loading");
    setSlots([]);
    void loadAvailability(requestInput, controller.signal).then((result) => {
      if (controller.signal.aborted || requestNumber.current !== thisRequest || result.kind === "aborted") {
        return;
      }
      if (result.kind === "forbidden") {
        setTimesState("forbidden");
        return;
      }
      if (result.kind === "error") {
        setTimesState("error");
        return;
      }
      setSlots(result.slots);
      setSelectedSlot((current) =>
        current !== null &&
        current.key === key &&
        result.slots.some((slot) => slot.startsAt === current.startsAt)
          ? current
          : null,
      );
      setTimesState(result.isOpen ? (result.slots.length === 0 ? "empty" : "ready") : "closed");
    });
    return () => controller.abort();
  }, [key, reloadKey, requestInput]);

  return {
    slots,
    timesState,
    selected,
    select: (startsAt: string) => setSelectedSlot({ key, startsAt }),
    clearSelection: () => setSelectedSlot(null),
    reload: () => setReloadKey((value) => value + 1),
  };
}

function availabilityKey(input: AvailabilityInput): string {
  if ("appointmentTypeId" in input) {
    return `${input.date}:${input.clinicianId}:type:${input.appointmentTypeId}`;
  }
  return `${input.date}:${input.clinicianId}:appointment:${input.rescheduleAppointmentId}`;
}
