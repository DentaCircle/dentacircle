import type { ApiResult, InventoryItem } from "@/lib/api/client";
import { listInventoryItems } from "@/lib/api/client";

const PAGE_SIZE = 100;

/** Every active item for the visit-type rule picker. The API caps each page at 100. */
export async function listActiveInventoryItemsForRules(
  cookieHeader: string,
): Promise<ApiResult<InventoryItem[]>> {
  const first = await listInventoryItems(cookieHeader, "active", "", "", 1, PAGE_SIZE);
  if (!first.ok) return first;
  const items = [...first.data.items];
  let page = 2;
  while (items.length < first.data.total) {
    const next = await listInventoryItems(cookieHeader, "active", "", "", page, PAGE_SIZE);
    if (!next.ok) return next;
    if (next.data.items.length === 0) break;
    items.push(...next.data.items);
    page += 1;
  }
  return { ok: true, data: items };
}
