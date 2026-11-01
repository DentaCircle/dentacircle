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
import { addCalendarDays } from "@/features/appointments/wall-time";

export type { BookChoice };

export function BookScreen({
  patientId,
  patient,
  types,
  clinicians,
  today,
  submitUrl,
  doneUrl,
  closedMessage,
}: {
  patientId?: string;
  patient: { full_name: string; display_id: string };
  types: BookChoice[];
  clinicians: BookChoice[];
  today: string;
  submitUrl: string;
  doneUrl: string;
  closedMessage?: string;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [typeId, setTypeId] = useState(types[0]?.id ?? "");
  const [clinicianId, setClinicianId] = useState(clinicians[0]?.id ?? "");
  const [date, setDate] = useState(today);
  const [message, setMessage] = useState<string | null>(null);
  const [isClosed, setIsClosed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const availabilityInput = useMemo(
    () => ({ date, clinicianId, appointmentTypeId: typeId }),
    [clinicianId, date, typeId],
  );
  const { slots, timesState, selected, select, clearSelection, reload } = useAvailability(availabilityInput);

  const selectedSlot = slots.find((slot) => slot.startsAt === selected);
  const selectedType = types.find((type) => type.id === typeId);
  const selectedClinician = clinicians.find((clinician) => clinician.id === clinicianId);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current || selected === null) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const payload: Record<string, string> = {
        clinician_id: clinicianId,
        appointment_type_id: typeId,
        starts_at: selected,
      };
      if (patientId !== undefined) payload.patient_id = patientId;
      const response = await fetchWithTimeout(submitUrl, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        router.push(doneUrl);
        router.refresh();
        return;
      }
      const errorBody: unknown = await response.json().catch(() => null);
      const code = errorCode(errorBody);
      const isClosedError =
        response.status === 404 || code === "invalid_status" || code === "patient_inactive";
      if (isClosedError) {
        if (closedMessage !== undefined) setIsClosed(true);
        else setMessage("Something went wrong.");
      } else if (response.status === 409) {
        setMessage(conflictMessage(code, "That time was just taken. Pick another."));
        clearSelection();
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

  if (isClosed && closedMessage !== undefined) {
    return <p role="alert">{closedMessage}</p>;
  }

  return (
    <form className="flex max-w-md flex-col gap-4" onSubmit={onSubmit}>
      <div className="rounded-lg border border-border bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">Booking for</p>
        <p className="font-semibold">{patient.full_name} <span className="font-normal">· {patient.display_id}</span></p>
      </div>
      <ChoiceField
        id="appointment_type_id"
        label="Appointment type"
        value={typeId}
        options={types}
        onChange={(value) => {
          setTypeId(value);
          clearSelection();
        }}
      />
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
      <section aria-label="Appointment summary" className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Appointment summary</h2>
        <p className="mt-2">{selectedType?.label} · {selectedClinician?.label}</p>
        <p>{date} · {selectedSlot ? `${selectedSlot.label}–${selectedSlot.endsAt}` : "Choose a time"}</p>
      </section>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting || selected === null || timesState !== "ready"}>
        Book appointment
      </Button>
    </form>
  );
}

