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
  if (state === "empty") return <div><p>No free times on this day.</p><p>Try another date, clinician or appointment type.</p></div>;
  if (state === "forbidden") return <p role="alert">You do not have access.</p>;
  if (state === "error") return <p role="alert">Something went wrong.</p>;
  return (
    <div className="space-y-4">
      {(["Morning", "Afternoon"] as const).map((period) => {
        const choices = slots.filter((slot) => (Number(slot.label.slice(0, 2)) < 12) === (period === "Morning"));
        if (choices.length === 0) return null;
        return (
          <div key={period} role="group" aria-label={`${period} free times`}>
            <p className="mb-2 text-sm font-medium">{period}</p>
            <div className="flex flex-wrap gap-2">
              {choices.map((slot) => (
                <Button key={slot.startsAt} type="button"
                  variant={selected === slot.startsAt ? "default" : "outline"}
                  aria-pressed={selected === slot.startsAt} onClick={() => onSelect(slot.startsAt)}>
                  {slot.label}
                </Button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
