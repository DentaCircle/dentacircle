import { Button } from "@/components/ui/button";
import type { SlotChoice } from "@/features/appointments/availability-request";

export type { SlotChoice } from "@/features/appointments/availability-request";

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
