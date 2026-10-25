import type { InventoryNotice } from "@/features/inventory/notices";
import type { InventoryListStatus } from "@/lib/api/client";

export type InventoryFilter = {
  status: InventoryListStatus;
  categoryId: string;
  query: string;
};

export function inventoryHref(
  filter: InventoryFilter,
  page = 1,
  notice?: InventoryNotice,
): string {
  const params = new URLSearchParams();
  params.set("status", filter.status);
  if (filter.categoryId !== "") params.set("category_id", filter.categoryId);
  if (filter.query !== "") params.set("q", filter.query);
  if (page > 1) params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  return `/inventory?${params.toString()}`;
}

export function inventoryItemHref(itemId: string, notice?: InventoryNotice, page = 1): string {
  const params = new URLSearchParams();
  if (page > 1) params.set("page", String(page));
  if (notice !== undefined) params.set("notice", notice);
  const query = params.toString();
  if (query === "") return `/inventory/${itemId}`;
  return `/inventory/${itemId}?${query}`;
}

export function pageFromQuery(value: string | undefined): number {
  if (value === undefined || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  if (!Number.isSafeInteger(page)) return 1;
  return page;
}

export function statusFromQuery(value: string | undefined): InventoryListStatus {
  if (value === "inactive" || value === "all") return value;
  return "active";
}
