export type CareNotice =
  | "plan_added"
  | "item_added"
  | "item_updated"
  | "started"
  | "completed"
  | "cancelled"
  | "changed";

export const CARE_NOTICES: Record<CareNotice, string> = {
  plan_added: "Care plan added.",
  item_added: "Item added.",
  item_updated: "Item updated.",
  started: "Marked started.",
  completed: "Marked completed.",
  cancelled: "Item cancelled.",
  changed: "This care item has already changed.",
};

const CARE_NOTICE_NAMES: readonly CareNotice[] = [
  "plan_added",
  "item_added",
  "item_updated",
  "started",
  "completed",
  "cancelled",
  "changed",
];

export function isCareNotice(value: string | undefined): value is CareNotice {
  return CARE_NOTICE_NAMES.some((notice) => notice === value);
}

export function careHref(patientId: string, notice?: CareNotice): string {
  if (notice === undefined) return `/patients/${patientId}/care`;
  return `/patients/${patientId}/care?notice=${notice}`;
}
