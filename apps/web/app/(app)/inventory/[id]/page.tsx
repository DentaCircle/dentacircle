import { requireUser } from "@/features/auth/current-user";
import { canReadInventory, canWriteInventory } from "@/features/inventory/access";
import {
  InventoryItemScreen,
  type InventoryItemScreenProps,
} from "@/features/inventory/item-screen";
import { pageFromQuery } from "@/features/inventory/links";
import { isInventoryNotice } from "@/features/inventory/notices";
import { detailBatches, historyEntry, inventoryRow, type HistoryView } from "@/features/inventory/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { getInventoryItem, listInventoryCategories, listInventoryTransactions } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type ItemPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ notice?: string; page?: string }>;
};

export default async function InventoryItemPage({ params, searchParams }: ItemPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const notice = isInventoryNotice(query.notice) ? query.notice : null;
  const historyPage = pageFromQuery(query.page);
  const user = await requireUser();
  if (!canReadInventory(user.roles)) {
    return <InventoryItemScreen {...blank("forbidden", notice, false)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [found, categories, movements] = await Promise.all([
    getInventoryItem(cookieHeader, id),
    listInventoryCategories(cookieHeader),
    listInventoryTransactions(cookieHeader, id, historyPage),
  ]);
  if (!found.ok) return <InventoryItemScreen {...failure(found.error, notice)} />;
  if (!categories.ok) return <InventoryItemScreen {...failure(categories.error, notice)} />;
  return (
    <InventoryItemScreen
      status="ready"
      item={inventoryRow(found.data)}
      batches={detailBatches(found.data)}
      categories={categories.data.map((category) => ({
        id: category.id,
        name: category.name,
        itemCount: category.item_count,
      }))}
      notice={notice}
      canWrite={canWriteInventory(user.roles)}
      history={historyFrom(movements, historyPage)}
    />
  );
}

function historyFrom(
  movements: Awaited<ReturnType<typeof listInventoryTransactions>>,
  page: number,
): HistoryView {
  if (!movements.ok) return { status: "error", rows: [], total: 0, page, pageSize: 20 };
  if (movements.data.total === 0) {
    return { status: "empty", rows: [], total: 0, page: movements.data.page, pageSize: movements.data.page_size };
  }
  return {
    status: "ready",
    rows: movements.data.items.map((row) => historyEntry(row)),
    total: movements.data.total,
    page: movements.data.page,
    pageSize: movements.data.page_size,
  };
}

function failure(
  error: { kind: string; status?: number },
  notice: InventoryItemScreenProps["notice"],
): InventoryItemScreenProps {
  if (error.kind === "api" && error.status === 403) return blank("forbidden", notice, false);
  if (error.kind === "api" && error.status === 404) return blank("not-found", notice, false);
  return blank("error", notice, false);
}

function blank(
  status: "not-found" | "forbidden" | "error",
  notice: InventoryItemScreenProps["notice"],
  canWrite: boolean,
): InventoryItemScreenProps {
  return {
    status,
    item: null,
    batches: [],
    categories: [],
    notice,
    canWrite,
    history: { status: "empty", rows: [], total: 0, page: 1, pageSize: 20 },
  };
}
