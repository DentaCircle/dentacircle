import { wallDate } from "@/features/appointments/wall-time";
import { dayHeading } from "@/features/calendar/dates";
import type { TimelineItem } from "@/lib/api/client";

export type TimelineDay = {
  date: string;
  heading: string;
  items: TimelineItem[];
};

/** Items are already newest first. A new day starts a new group. */
export function groupByDay(items: readonly TimelineItem[]): TimelineDay[] {
  const groups: TimelineDay[] = [];
  for (const item of items) {
    const date = wallDate(item.occurred_at);
    if (date === null) continue;
    const last = groups[groups.length - 1];
    if (last === undefined || last.date !== date) {
      groups.push({ date, heading: dayHeading(date), items: [item] });
    } else {
      last.items.push(item);
    }
  }
  return groups;
}
