"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchWithTimeout } from "@/lib/api/transport";
import { ChoiceField, type BookChoice } from "@/features/appointments/choice-field";
import { conflictMessage, errorCode } from "@/features/appointments/request-errors";
import { TimeSlots } from "@/features/appointments/time-slots";
import { useAvailability } from "@/features/appointments/use-availability";
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
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const availabilityInput = useMemo(
    () => ({ date, clinicianId, rescheduleAppointmentId: appointmentId }),
    [appointmentId, clinicianId, date],
  );
  const { slots, timesState, selected, select, clearSelection, reload } = useAvailability(availabilityInput);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current || selected === null) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const body: { starts_at: string; clinician_id?: string } = { starts_at: selected };
      if (clinicianId !== initialClinicianId) body.clinician_id = clinicianId;
      const response = await fetchWithTimeout(`/api/appointments/${appointmentId}/reschedule`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(body),
      });
      if (response.ok) {
        const day = wallDate(selected);
        router.push(`/calendar?view=day&date=${day ?? date}&notice=rescheduled`);
        router.refresh();
        return;
      }
      if (response.status === 409) {
        const code = errorCode(await response.json().catch(() => null));
        clearSelection();
        setMessage(conflictMessage(code, "That time is not available. Pick another."));
        reload();
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
          clearSelection();
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
            clearSelection();
          }}
        />
      </div>
      <TimeSlots state={timesState} slots={slots} selected={selected} onSelect={select} />
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting || selected === null || timesState !== "ready"}>
        Reschedule
      </Button>
    </form>
  );
}
