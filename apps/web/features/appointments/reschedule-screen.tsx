"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChoiceField, type BookChoice } from "@/features/appointments/choice-field";
import {
  isAbort,
  parseAvailability,
  TimeSlots,
  type SlotChoice,
  type TimesState,
} from "@/features/appointments/time-slots";
import { addCalendarDays, wallDate } from "@/features/appointments/wall-time";

export function RescheduleScreen({
  appointmentId,
  clinicians,
  initialClinicianId,
  initialDate,
  today,
}: {
  appointmentId: string;
  clinicians: BookChoice[];
  initialClinicianId: string;
  initialDate: string;
  today: string;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [clinicianId, setClinicianId] = useState(initialClinicianId);
  const [date, setDate] = useState(initialDate);
  const [slots, setSlots] = useState<SlotChoice[]>([]);
  const [timesState, setTimesState] = useState<TimesState>("loading");
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setTimesState("loading");
    setSlots([]);
    const params = new URLSearchParams({
      date,
      clinician_id: clinicianId,
      reschedule_appointment_id: appointmentId,
    });
    void fetch(`/api/appointments/availability?${params.toString()}`, {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 403) {
          setTimesState("forbidden");
          return;
        }
        if (!response.ok) {
          setTimesState("error");
          return;
        }
        const parsed = parseAvailability(await response.json());
        if (parsed === null) {
          setTimesState("error");
          return;
        }
        setSlots(parsed.slots);
        setSelected((current) =>
          current !== null && parsed.slots.some((slot) => slot.startsAt === current) ? current : null,
        );
        if (!parsed.isOpen) {
          setTimesState("closed");
          return;
        }
        setTimesState(parsed.slots.length === 0 ? "empty" : "ready");
      })
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        setTimesState("error");
      });
    return () => controller.abort();
  }, [appointmentId, clinicianId, date, reloadKey]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current || selected === null) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/appointments/${appointmentId}/reschedule`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ clinician_id: clinicianId, starts_at: selected }),
      });
      if (response.ok) {
        const day = wallDate(selected);
        router.push(`/calendar?view=day&date=${day ?? date}&notice=rescheduled`);
        router.refresh();
        return;
      }
      if (response.status === 409) {
        setSelected(null);
        setMessage("That time is not available. Pick another.");
        setReloadKey((current) => current + 1);
      } else if (response.status === 403) {
        setMessage("You do not have access.");
      } else {
        setMessage("Something went wrong.");
      }
    } catch {
      setMessage("Could not reach the server.");
    }
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form className="flex max-w-md flex-col gap-4" onSubmit={onSubmit}>
      <ChoiceField
        id="clinician_id"
        label="Clinician"
        value={clinicianId}
        options={clinicians}
        onChange={(value) => {
          setClinicianId(value);
          setSelected(null);
        }}
      />
      <div className="flex flex-col gap-2">
        <Label htmlFor="date">Date</Label>
        <Input
          id="date"
          type="date"
          value={date}
          min={today}
          max={addCalendarDays(today, 365)}
          onChange={(event) => {
            setDate(event.target.value);
            setSelected(null);
          }}
        />
      </div>
      <TimeSlots state={timesState} slots={slots} selected={selected} onSelect={setSelected} />
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting || selected === null}>
        Reschedule
      </Button>
    </form>
  );
}
