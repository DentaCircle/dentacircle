import type { BookChoice } from "@/features/appointments/choice-field";

export function clinicianChoices(assigned: BookChoice, active: readonly BookChoice[]): BookChoice[] {
  if (active.some((row) => row.id === assigned.id)) return [...active];
  return [assigned, ...active];
}
