import { addCalendarDays } from "@/features/appointments/wall-time";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

export function mondayOfWeek(isoDate: string): string {
  const parts = isoParts(isoDate);
  if (parts === null) throw new Error("The clinic date could not be read.");
  const utc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  const weekday = utc.getUTCDay();
  const back = weekday === 0 ? 6 : weekday - 1;
  return addCalendarDays(isoDate, -back);
}

export function dayHeading(isoDate: string): string {
  const parts = isoParts(isoDate);
  if (parts === null) throw new Error("The clinic date could not be read.");
  const utc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  return `${WEEKDAYS[utc.getUTCDay()]} ${parts.day} ${MONTHS[parts.month - 1]}`;
}

export function isIsoDate(value: string): boolean {
  const parts = isoParts(value);
  if (parts === null) return false;
  const utc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  return (
    utc.getUTCFullYear() === parts.year &&
    utc.getUTCMonth() === parts.month - 1 &&
    utc.getUTCDate() === parts.day
  );
}

function isoParts(value: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}
