import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { CategoryPanel, type CategoryOption } from "@/features/inventory/category-panel";
import { AddItemForm } from "@/features/inventory/item-form";
import { inventoryHref, inventoryItemHref, type InventoryFilter } from "@/features/inventory/links";
import { INVENTORY_NOTICES, type InventoryNotice } from "@/features/inventory/notices";
import type { InventoryRow } from "@/features/inventory/rows";
import type { InventoryListStatus } from "@/lib/api/client";

const STATUS_LINKS: { status: InventoryListStatus; label: string }[] = [
  { status: "active", label: "Active" },
  { status: "inactive", label: "Inactive" },
  { status: "all", label: "All" },
];

export type InventoryListScreenProps = {
  status: "ready" | "empty" | "forbidden" | "error";
  rows: InventoryRow[];
  categories: CategoryOption[];
  total: number;
  page: number;
  pageSize: number;
  filter: InventoryFilter;
  notice: InventoryNotice | null;
  canWrite: boolean;
};

export function InventoryListScreen({
  status,
  rows,
  categories,
  total,
  page,
  pageSize,
  filter,
  notice,
  canWrite,
}: InventoryListScreenProps) {
  const formKey = `${filter.status}:${filter.categoryId}:${filter.query}:${notice ?? ""}`;
  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Inventory</h1>
      {notice === null ? null : <p role="status">{INVENTORY_NOTICES[notice]}</p>}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Inventory could not be loaded.</p> : null}
      {status === "forbidden" || status === "error" ? null : (
        <>
          <StatusLinks filter={filter} />
          <CategoryLinks categories={categories} filter={filter} />
          <SearchForm filter={filter} />
          <CategoryPanel
            key={`categories:${formKey}`}
            categories={categories}
            filter={filter}
            canWrite={canWrite}
          />
          {canWrite ? (
            <AddItemForm key={`item:${formKey}`} categories={categories} filter={filter} />
          ) : null}
        </>
      )}
      {status === "empty" ? <p>No inventory items yet.</p> : null}
      {status === "ready" ? (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium" scope="col">
                  Name
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Category
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Unit
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Threshold
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Batches
                </th>
                <th className="py-2 font-medium" scope="col">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b">
                  <td className="py-2 pr-3">
                    <Link href={inventoryItemHref(row.id)} className="font-medium underline">
                      {row.name}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{row.categoryName}</td>
                  <td className="py-2 pr-3">{row.unit}</td>
                  <td className="py-2 pr-3">{row.threshold}</td>
                  <td className="py-2 pr-3">{row.batchCount}</td>
                  <td className="py-2">
                    <Badge variant={row.status === "active" ? "secondary" : "outline"}>
                      {row.statusLabel}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav aria-label="Pages" className="flex gap-3">
            {page > 1 ? (
              <Link href={inventoryHref(filter, page - 1)}>Previous</Link>
            ) : (
              <span>Previous</span>
            )}
            {page * pageSize < total ? (
              <Link href={inventoryHref(filter, page + 1)}>Next</Link>
            ) : (
              <span>Next</span>
            )}
          </nav>
        </>
      ) : null}
    </section>
  );
}

function StatusLinks({ filter }: { filter: InventoryFilter }) {
  return (
    <nav aria-label="Item status" className="flex gap-3 text-sm">
      {STATUS_LINKS.map((link) => (
        <Link
          key={link.status}
          href={inventoryHref({ ...filter, status: link.status })}
          aria-current={filter.status === link.status ? "page" : undefined}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}

function CategoryLinks({
  categories,
  filter,
}: {
  categories: CategoryOption[];
  filter: InventoryFilter;
}) {
  return (
    <nav aria-label="Category" className="flex flex-wrap gap-3 text-sm">
      <Link
        href={inventoryHref({ ...filter, categoryId: "" })}
        aria-current={filter.categoryId === "" ? "page" : undefined}
      >
        All categories
      </Link>
      {categories.map((category) => (
        <Link
          key={category.id}
          href={inventoryHref({ ...filter, categoryId: category.id })}
          aria-current={filter.categoryId === category.id ? "page" : undefined}
        >
          {category.name}
        </Link>
      ))}
    </nav>
  );
}

function SearchForm({ filter }: { filter: InventoryFilter }) {
  return (
    <form method="get" action="/inventory" className="flex flex-wrap items-end gap-2">
      <input type="hidden" name="status" value={filter.status} />
      {filter.categoryId === "" ? null : (
        <input type="hidden" name="category_id" value={filter.categoryId} />
      )}
      <div className="flex flex-col gap-1">
        <label htmlFor="inventory-search" className="text-sm font-medium">
          Search by name
        </label>
        <input
          id="inventory-search"
          name="q"
          defaultValue={filter.query}
          className="h-9 rounded-md border px-2 text-sm"
        />
      </div>
      <button type="submit" className="h-9 rounded-md border px-3 text-sm">
        Search
      </button>
    </form>
  );
}
