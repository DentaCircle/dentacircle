import type { DocumentNotice } from "@/features/documents/notices";

export function documentsHref(patientId: string, page = 1, notice?: DocumentNotice): string {
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  return `/patients/${patientId}/documents?${params.toString()}`;
}

/** The download goes through the same `/api` rewrite as every browser call. */
export function downloadHref(patientId: string, documentId: string): string {
  return `/api/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}/file`;
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}
