"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addCalendarDays, wallTime } from "@/features/appointments/wall-time";

export type BookChoice = {
  id: string;
  label: string;
};

type Slot = {
  startsAt: string;
  label: string;
};

type TimesState = "loading" | "closed" | "empty" | "ready" | "forbidden" | "error";

export function BookScreen({
  patientId,
  types,
  clinicians,
  today,
}: {
  patientId: string;
  types: BookChoice[];
  clinicians: BookChoice[];
  today: string;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [typeId, setTypeId] = useState(types[0]?.id ?? "");
  const [clinicianId, setClinicianId] = useState(clinicians[0]?.id ?? "");
  const [date, setDate] = useState(today);
  const [slots, setSlots] = useState<Slot[]>([]);
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
      const response = await fetch("/api/appointments", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          patient_id: patientId,
          clinician_id: clinicianId,
          appointment_type_id: typeId,
          starts_at: selected,
        }),
      });
      if (response.ok) {
        router.push(`/patients/${patientId}?booked=1`);
        router.refresh();
        return;
      }
      if (response.status === 409) {
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

  return (
    <form className="flex max-w-md flex-col gap-4" onSubmit={onSubmit}>
      <Choice
        id="appointment_type_id"
        label="Type"
        value={typeId}
        options={types}
        onChange={(value) => {
          setTypeId(value);
          setSelected(null);
        }}
      />
      <Choice
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
      <Times state={timesState} slots={slots} selected={selected} onSelect={setSelected} />
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

function Choice({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: BookChoice[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Times({
  state,
  slots,
  selected,
  onSelect,
}: {
  state: TimesState;
  slots: Slot[];
  selected: string | null;
  onSelect: (startsAt: string) => void;
}) {
  if (state === "loading") return <p>Loading times…</p>;
  if (state === "closed") return <p>The clinic is closed on this day.</p>;
  if (state === "empty") return <p>No free times on this day.</p>;
  if (state === "forbidden") return <p role="alert">You do not have access.</p>;
  if (state === "error") return <p role="alert">Something went wrong.</p>;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Free times">
      {slots.map((slot) => (
        <Button
          key={slot.startsAt}
          type="button"
          variant={selected === slot.startsAt ? "default" : "outline"}
          aria-pressed={selected === slot.startsAt}
          onClick={() => onSelect(slot.startsAt)}
        >
          {slot.label}
        </Button>
      ))}
    </div>
  );
}

function parseAvailability(value: unknown): { isOpen: boolean; slots: Slot[] } | null {
  if (typeof value !== "object" || value === null || !("is_open" in value) || !("slots" in value)) {
    return null;
  }
  if (typeof value.is_open !== "boolean" || !Array.isArray(value.slots)) return null;
  const slots: Slot[] = [];
  for (const slot of value.slots) {
    if (typeof slot !== "object" || slot === null || !("starts_at" in slot)) return null;
    if (typeof slot.starts_at !== "string") return null;
    const label = wallTime(slot.starts_at);
    if (label === null) return null;
    slots.push({ startsAt: slot.starts_at, label });
  }
  return { isOpen: value.is_open, slots };
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
