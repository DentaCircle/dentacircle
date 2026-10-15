import { Button } from "@/components/ui/button";
import { wallTime } from "@/features/appointments/wall-time";

export type SlotChoice = {
  startsAt: string;
  label: string;
};

export type TimesState = "loading" | "closed" | "empty" | "ready" | "forbidden" | "error";

export function TimeSlots({
  state,
  slots,
  selected,
  onSelect,
}: {
  state: TimesState;
  slots: SlotChoice[];
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

export function parseAvailability(value: unknown): { isOpen: boolean; slots: SlotChoice[] } | null {
  if (typeof value !== "object" || value === null || !("is_open" in value) || !("slots" in value)) {
    return null;
  }
  if (typeof value.is_open !== "boolean" || !Array.isArray(value.slots)) return null;
  const slots: SlotChoice[] = [];
  for (const slot of value.slots) {
    if (typeof slot !== "object" || slot === null || !("starts_at" in slot)) return null;
    if (typeof slot.starts_at !== "string") return null;
    const label = wallTime(slot.starts_at);
    if (label === null) return null;
    slots.push({ startsAt: slot.starts_at, label });
  }
  return { isOpen: value.is_open, slots };
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
