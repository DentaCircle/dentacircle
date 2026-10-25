import { formatDueOn } from "@/features/care/follow-up-line";
import type {
  InventoryBatch,
  InventoryItem,
  InventoryItemDetail,
  StockTransaction,
} from "@/lib/api/client";

export type InventoryRow = {
  id: string;
  name: string;
  categoryName: string;
  unit: string;
  threshold: number;
  batchCount: number;
  stock: number;
  status: InventoryItem["status"];
  statusLabel: string;
};

export type BatchRow = {
  id: string;
  batchNumber: string;
  expiryOn: string | null;
  expiryLabel: string;
  expired: boolean;
  quantity: number;
};

export type HistoryEntry = {
  id: string;
  typeLabel: string;
  reasonLabel: string;
  changeLabel: string;
  batchNumber: string;
  recordedBy: string;
  whenLabel: string;
};

export type HistoryView = {
  status: "ready" | "empty" | "error";
  rows: HistoryEntry[];
  total: number;
  page: number;
  pageSize: number;
};

export function inventoryRow(item: InventoryItem): InventoryRow {
  return {
    id: item.id,
    name: item.name,
    categoryName: item.category.name,
    unit: item.unit,
    threshold: item.low_stock_threshold,
    batchCount: item.batch_count,
    stock: item.stock,
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
    quantity: batch.quantity,
  };
}

const TYPE_LABELS = { restock: "Restock", adjustment: "Adjustment" } as const;
const REASON_LABELS = { damaged: "Damaged", expired: "Expired", correction: "Correction" } as const;

export function historyEntry(row: StockTransaction): HistoryEntry {
  const change =
    row.quantity_change > 0 ? `+${row.quantity_change}` : String(row.quantity_change);
  return {
    id: row.id,
    typeLabel: TYPE_LABELS[row.type],
    reasonLabel: row.reason === null ? "—" : REASON_LABELS[row.reason],
    changeLabel: change,
    batchNumber: row.batch.batch_number,
    recordedBy: row.recorded_by,
    whenLabel: formatRecordedAt(row.created_at),
  };
}

export function formatRecordedAt(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (match === null) return value;
  return `${formatDueOn(`${match[1]}-${match[2]}-${match[3]}`)}, ${match[4]}:${match[5]}`;
}

export function detailBatches(item: InventoryItemDetail): BatchRow[] {
  return item.batches.map((batch) => batchRow(batch));
}
