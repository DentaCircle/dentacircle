import Link from "next/link";
import { Fragment } from "react";

import { Badge } from "@/components/ui/badge";
import { AddBatchForm, EditBatchForm, ItemStatusButton } from "@/features/inventory/batch-forms";
import type { CategoryOption } from "@/features/inventory/category-panel";
import { HistoryPanel } from "@/features/inventory/history-panel";
import { EditItemForm } from "@/features/inventory/item-form";
import { INVENTORY_NOTICES, type InventoryNotice } from "@/features/inventory/notices";
import type { BatchRow, HistoryView, InventoryRow } from "@/features/inventory/rows";
import { AddStockForm, AdjustForm } from "@/features/inventory/stock-forms";

export type InventoryItemScreenProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  item: InventoryRow | null;
  batches: BatchRow[];
  categories: CategoryOption[];
  notice: InventoryNotice | null;
  canWrite: boolean;
  history?: HistoryView;
};

export function InventoryItemScreen({
  status,
  item,
  batches,
  categories,
  notice,
  canWrite,
  history = { status: "empty", rows: [], total: 0, page: 1, pageSize: 20 },
}: InventoryItemScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <p>
        <Link href="/inventory">Inventory</Link>
      </p>
      <h1 className="flex flex-wrap items-baseline gap-3 text-2xl font-semibold">
        <span>{item === null ? "Inventory item" : item.name}</span>
        {item === null ? null : <span className="text-lg font-normal">Stock {item.stock}</span>}
      </h1>
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
          {batches.length === 0 ? null : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium" scope="col">
                    Batch
                  </th>
                  <th className="py-2 pr-3 font-medium" scope="col">
                    Expiry
                  </th>
                  <th className="py-2 font-medium" scope="col">
                    Quantity
                  </th>
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <Fragment key={batch.id}>
                    <tr className="border-b">
                      <td className="py-2 pr-3">
                        <span className="mr-2">{batch.batchNumber}</span>
                        {batch.expired ? <Badge variant="destructive">Expired</Badge> : null}
                      </td>
                      <td className="py-2 pr-3">{batch.expiryLabel}</td>
                      <td className="py-2">{batch.quantity}</td>
                    </tr>
                    {canWrite ? (
                      <tr className="border-b">
                        <td className="py-2" colSpan={3}>
                          <div className="flex flex-col gap-3">
                            {item.status === "active" ? (
                              <AddStockForm itemId={item.id} batchId={batch.id} />
                            ) : null}
                            <AdjustForm itemId={item.id} batchId={batch.id} />
                            <EditBatchForm
                              key={`${batch.id}:${notice ?? ""}`}
                              itemId={item.id}
                              batch={batch}
                            />
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
          <HistoryPanel itemId={item.id} history={history} />
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
