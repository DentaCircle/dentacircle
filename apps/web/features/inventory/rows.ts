import { formatDueOn } from "@/features/care/follow-up-line";
import type { InventoryBatch, InventoryItem, InventoryItemDetail } from "@/lib/api/client";

export type InventoryRow = {
  id: string;
  name: string;
  categoryName: string;
  unit: string;
  threshold: number;
  batchCount: number;
  status: InventoryItem["status"];
  statusLabel: string;
};

export type BatchRow = {
  id: string;
  batchNumber: string;
  expiryOn: string | null;
  expiryLabel: string;
  expired: boolean;
};

export function inventoryRow(item: InventoryItem): InventoryRow {
  return {
    id: item.id,
    name: item.name,
    categoryName: item.category.name,
    unit: item.unit,
    threshold: item.low_stock_threshold,
    batchCount: item.batch_count,
    status: item.status,
    statusLabel: item.status === "active" ? "Active" : "Inactive",
  };
}

export function batchRow(batch: InventoryBatch): BatchRow {
  return {
    id: batch.id,
    batchNumber: batch.batch_number,
    expiryOn: batch.expiry_on,
    expiryLabel: batch.expiry_on === null ? "No expiry" : formatDueOn(batch.expiry_on),
    expired: batch.expired,
  };
}

export function detailBatches(item: InventoryItemDetail): BatchRow[] {
  return item.batches.map((batch) => batchRow(batch));
}
