import { requireUser } from "@/features/auth/current-user";
import { canReadInventory, canWriteInventory } from "@/features/inventory/access";
import {
  InventoryItemScreen,
  type InventoryItemScreenProps,
} from "@/features/inventory/item-screen";
import { isInventoryNotice } from "@/features/inventory/notices";
import { detailBatches, inventoryRow } from "@/features/inventory/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { getInventoryItem, listInventoryCategories } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type ItemPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ notice?: string }>;
};

export default async function InventoryItemPage({ params, searchParams }: ItemPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const notice = isInventoryNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canReadInventory(user.roles)) {
    return <InventoryItemScreen {...blank("forbidden", notice, false)} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [found, categories] = await Promise.all([
    getInventoryItem(cookieHeader, id),
    listInventoryCategories(cookieHeader),
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
    />
  );
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
  return { status, item: null, batches: [], categories: [], notice, canWrite };
}
