import type { RecallQueueView } from "@/lib/api/client";

export type QueueNotice = "contacted" | "booked" | "changed" | "cancelled";

const NOTICES: Record<QueueNotice, string> = {
  contacted: "Marked contacted.",
  booked: "Visit booked.",
  changed: "This recall has already changed.",
  cancelled: "Recall cancelled.",
};

const NOTICE_NAMES: readonly QueueNotice[] = ["contacted", "booked", "changed", "cancelled"];

export function recallsHref(view: RecallQueueView, page: number, notice?: QueueNotice): string {
  const params = new URLSearchParams();
  if (view !== "due") params.set("view", view);
  params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  return `/recalls?${params.toString()}`;
}

export function viewFromQuery(value: string | undefined): RecallQueueView {
  if (value === "all") return "all";
  return "due";
}

export function noticeFromQuery(value: string | undefined): QueueNotice | null {
  if (value === undefined) return null;
  const match = NOTICE_NAMES.find((notice) => notice === value);
  return match ?? null;
}

export function noticeText(notice: QueueNotice): string {
  return NOTICES[notice];
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}
