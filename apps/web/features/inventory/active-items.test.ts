import { beforeEach, describe, expect, it, vi } from "vitest";

import { listActiveInventoryItemsForRules } from "@/features/inventory/active-items";
import { listInventoryItems } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  listInventoryItems: vi.fn(),
}));

const item = (id: string, name: string) => ({
  id,
  name,
  category: { id: "cat-1", name: "Consumables" },
  unit: "box",
  low_stock_threshold: 0,
  status: "active" as const,
  batch_count: 1,
  stock: 5,
  usable_stock: 5,
  alerts: [],
});

describe("listActiveInventoryItemsForRules", () => {
  beforeEach(() => {
    vi.mocked(listInventoryItems).mockReset();
  });

  it("loads every page when more than 100 active items exist", async () => {
    vi.mocked(listInventoryItems)
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: Array.from({ length: 100 }, (_, index) => item(`id-${index}`, `Item ${index}`)),
          total: 150,
          page: 1,
          page_size: 100,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: Array.from({ length: 50 }, (_, index) => item(`id-${index + 100}`, `Item ${index + 100}`)),
          total: 150,
          page: 2,
          page_size: 100,
        },
      });

    const result = await listActiveInventoryItemsForRules("dc_session=x");
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data).toHaveLength(150);
    expect(listInventoryItems).toHaveBeenCalledTimes(2);
    expect(listInventoryItems).toHaveBeenNthCalledWith(2, "dc_session=x", "active", "", "", 2, 100);
  });

  it("stops when a later page is empty even if total is still higher", async () => {
    vi.mocked(listInventoryItems)
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: Array.from({ length: 100 }, (_, index) => item(`id-${index}`, `Item ${index}`)),
          total: 200,
          page: 1,
          page_size: 100,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          items: [],
          total: 200,
          page: 2,
          page_size: 100,
        },
      });

    const result = await listActiveInventoryItemsForRules("dc_session=x");
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data).toHaveLength(100);
    expect(listInventoryItems).toHaveBeenCalledTimes(2);
  });
});
