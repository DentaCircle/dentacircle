"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChoiceField, type BookChoice } from "@/features/appointments/choice-field";
import { isAbort, parseAvailability, TimeSlots, type SlotChoice, type TimesState } from "@/features/appointments/time-slots";
import { addCalendarDays } from "@/features/appointments/wall-time";

export type { BookChoice };

export function BookScreen({
  patientId,
  types,
  clinicians,
  today,
  submitUrl,
  doneUrl,
  closedMessage,
}: {
  patientId?: string;
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
  const [slots, setSlots] = useState<SlotChoice[]>([]);
  const [timesState, setTimesState] = useState<TimesState>("loading");
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isClosed, setIsClosed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setTimesState("loading");
    setSlots([]);
    const params = new URLSearchParams({
      date,
      clinician_id: clinicianId,
      appointment_type_id: typeId,
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
  }, [clinicianId, typeId, date, reloadKey]);

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
      const response = await fetch(submitUrl, {
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
        setSelected(null);
        setMessage("That time was just taken. Pick another.");
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

  if (isClosed && closedMessage !== undefined) {
    return <p role="alert">{closedMessage}</p>;
  }

  return (
    <form className="flex max-w-md flex-col gap-4" onSubmit={onSubmit}>
      <ChoiceField
        id="appointment_type_id"
        label="Type"
        value={typeId}
        options={types}
        onChange={(value) => {
          setTypeId(value);
          setSelected(null);
        }}
      />
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
        Book
      </Button>
    </form>
  );
}

function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("error" in body)) return null;
  const error = body.error;
  if (typeof error !== "object" || error === null || !("code" in error)) return null;
  return typeof error.code === "string" ? error.code : null;
}

