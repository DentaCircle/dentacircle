export type PatientStatusFilter = "all" | "active" | "inactive";

export function patientsHref(
  query: string,
  page: number,
  status: PatientStatusFilter = "all",
): string {
  const params = new URLSearchParams();
  if (query !== "") params.set("q", query);
  if (status !== "all") params.set("status", status);
  params.set("page", String(page));
  return `/patients?${params.toString()}`;
}

export function statusFromQuery(value: string | undefined): PatientStatusFilter | "invalid" {
  if (value === undefined || value === "") return "all";
  if (value === "active" || value === "inactive") return value;
  return "invalid";
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}

export function createdDisplayId(value: string | undefined): string | null {
  if (value === undefined || !/^P-\d{4,}$/.test(value)) return null;
  return value;
}
