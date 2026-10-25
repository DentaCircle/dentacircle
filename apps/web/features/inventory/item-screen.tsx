import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { AddBatchForm, EditBatchForm, ItemStatusButton } from "@/features/inventory/batch-forms";
import type { CategoryOption } from "@/features/inventory/category-panel";
import { EditItemForm } from "@/features/inventory/item-form";
import { INVENTORY_NOTICES, type InventoryNotice } from "@/features/inventory/notices";
import type { BatchRow, InventoryRow } from "@/features/inventory/rows";

export type InventoryItemScreenProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  item: InventoryRow | null;
  batches: BatchRow[];
  categories: CategoryOption[];
  notice: InventoryNotice | null;
  canWrite: boolean;
};

export function InventoryItemScreen({
  status,
  item,
  batches,
  categories,
  notice,
  canWrite,
}: InventoryItemScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <p>
        <Link href="/inventory">Inventory</Link>
      </p>
      <h1 className="text-2xl font-semibold">{item === null ? "Inventory item" : item.name}</h1>
      {notice === null ? null : <p role="status">{INVENTORY_NOTICES[notice]}</p>}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "error" ? <p role="alert">Inventory could not be loaded.</p> : null}
      {status === "ready" && item !== null ? (
        <>
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
            <dt>Category</dt>
            <dd>{item.categoryName}</dd>
            <dt>Unit</dt>
            <dd>{item.unit}</dd>
            <dt>Threshold</dt>
            <dd>{item.threshold}</dd>
            <dt>Status</dt>
            <dd>
              <Badge variant={item.status === "active" ? "secondary" : "outline"}>
                {item.statusLabel}
              </Badge>
            </dd>
          </dl>
          {canWrite ? (
            <>
              <EditItemForm
                key={`${item.id}:${notice ?? ""}`}
                itemId={item.id}
                categories={categories}
                initial={{
                  name: item.name,
                  categoryId: categoryId(categories, item.categoryName),
                  unit: item.unit,
                  threshold: String(item.threshold),
                }}
              />
              <ItemStatusButton
                key={`${item.id}:${item.status}`}
                itemId={item.id}
                status={item.status}
              />
            </>
          ) : null}
          <h2 className="text-lg font-medium">Batches</h2>
          {batches.length === 0 ? <p>No batches yet.</p> : null}
          <ul className="flex flex-col gap-3">
            {batches.map((batch) => (
              <li key={batch.id} className="flex flex-col gap-2 border-b pb-3">
                <p className="flex flex-wrap items-center gap-2">
                  <span>{batch.batchNumber}</span>
                  <span>{batch.expiryLabel}</span>
                  {batch.expired ? <Badge variant="destructive">Expired</Badge> : null}
                </p>
                {canWrite ? (
                  <EditBatchForm
                    key={`${batch.id}:${notice ?? ""}`}
                    itemId={item.id}
                    batch={batch}
                  />
                ) : null}
              </li>
            ))}
          </ul>
          {canWrite ? (
            <AddBatchForm
              key={`${item.id}:${item.status}:${notice ?? ""}`}
              itemId={item.id}
              inactive={item.status === "inactive"}
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function categoryId(categories: CategoryOption[], name: string): string {
  return categories.find((category) => category.name === name)?.id ?? "";
}
