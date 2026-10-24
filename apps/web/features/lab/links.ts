import type { LabNotice } from "@/features/lab/notices";
import type { LabWorkListView } from "@/lib/api/client";

export function patientLabHref(patientId: string, page = 1, notice?: LabNotice): string {
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  return `/patients/${patientId}/lab?${params.toString()}`;
}

export function clinicLabHref(view: LabWorkListView, page = 1, notice?: LabNotice): string {
  const params = new URLSearchParams();
  params.set("view", view);
  params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  return `/lab?${params.toString()}`;
}

export function labDocumentsHref(patientId: string, labWorkId: string): string {
  return `/patients/${patientId}/documents?lab_work_id=${encodeURIComponent(labWorkId)}`;
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}

export function viewFromQuery(value: string | undefined): LabWorkListView {
  return value === "all" ? "all" : "open";
}
