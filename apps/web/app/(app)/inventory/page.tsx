import { requireUser } from "@/features/auth/current-user";
import { canReadInventory, canWriteInventory } from "@/features/inventory/access";
import { InventoryListScreen, type InventoryListScreenProps } from "@/features/inventory/list-screen";
import { pageFromQuery, statusFromQuery, type InventoryFilter } from "@/features/inventory/links";
import { isInventoryNotice } from "@/features/inventory/notices";
import { inventoryRow } from "@/features/inventory/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { listInventoryCategories, listInventoryItems } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type InventoryPageProps = {
  searchParams: Promise<{
    status?: string;
    category_id?: string;
    q?: string;
    page?: string;
    notice?: string;
  }>;
};

export default async function InventoryPage({ searchParams }: InventoryPageProps) {
  const query = await searchParams;
  const filter: InventoryFilter = {
    status: statusFromQuery(query.status),
    categoryId: query.category_id ?? "",
    query: query.q ?? "",
  };
  const page = pageFromQuery(query.page);
  const notice = isInventoryNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canReadInventory(user.roles)) {
    return <InventoryListScreen {...blank("forbidden", filter, page, notice, false)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [categories, items] = await Promise.all([
    listInventoryCategories(cookieHeader),
    listInventoryItems(cookieHeader, filter.status, filter.categoryId, filter.query, page),
  ]);
  if (!categories.ok || !items.ok) {
    const forbidden =
      (categories.ok === false && categories.error.kind === "api" && categories.error.status === 403) ||
      (items.ok === false && items.error.kind === "api" && items.error.status === 403);
    return (
      <InventoryListScreen
        {...blank(forbidden ? "forbidden" : "error", filter, page, notice, canWriteInventory(user.roles))}
      />
    );
  }
  const categoryOptions = categories.data.map((category) => ({
    id: category.id,
    name: category.name,
    itemCount: category.item_count,
  }));
  return (
    <InventoryListScreen
      status={items.data.total === 0 ? "empty" : "ready"}
      rows={items.data.items.map((item) => inventoryRow(item))}
      categories={categoryOptions}
      total={items.data.total}
      page={items.data.page}
      pageSize={items.data.page_size}
      filter={filter}
      notice={notice}
      canWrite={canWriteInventory(user.roles)}
    />
  );
}

function blank(
  status: "forbidden" | "error",
  filter: InventoryFilter,
  page: number,
  notice: InventoryListScreenProps["notice"],
  canWrite: boolean,
): InventoryListScreenProps {
  return {
    status,
    rows: [],
    categories: [],
    total: 0,
    page,
    pageSize: 20,
    filter,
    notice,
    canWrite,
  };
}
