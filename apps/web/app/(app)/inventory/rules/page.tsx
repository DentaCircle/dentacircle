import { requireUser } from "@/features/auth/current-user";
import { canReadInventory, canWriteInventory } from "@/features/inventory/access";
import { RulesScreen, type RulesNotice, type VisitTypeRules } from "@/features/inventory/rules-screen";
import { sessionCookieHeader } from "@/features/patients/session";
import { listActiveInventoryItemsForRules } from "@/features/inventory/active-items";
import { listAppointmentTypes, listResourceRules } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type RulesPageProps = {
  searchParams: Promise<{ notice?: string }>;
};

export default async function RulesPage({ searchParams }: RulesPageProps) {
  const notice = ruleNotice((await searchParams).notice);
  const user = await requireUser();
  if (!canReadInventory(user.roles)) {
    return <RulesScreen status="forbidden" types={[]} items={[]} canWrite={false} notice={notice} />;
  }
  const cookieHeader = await sessionCookieHeader();
  const [types, items] = await Promise.all([
    listAppointmentTypes(cookieHeader),
    listActiveInventoryItemsForRules(cookieHeader),
  ]);
  if (!types.ok || !items.ok) {
    const forbidden =
      (types.ok === false && types.error.kind === "api" && types.error.status === 403) ||
      (items.ok === false && items.error.kind === "api" && items.error.status === 403);
    return (
      <RulesScreen
        status={forbidden ? "forbidden" : "error"}
        types={[]}
        items={[]}
        canWrite={canWriteInventory(user.roles)}
        notice={notice}
      />
    );
  }
  const sections: VisitTypeRules[] = [];
  for (const type of types.data) {
    const rules = await listResourceRules(cookieHeader, type.id);
    if (!rules.ok) {
      return (
        <RulesScreen
          status={rules.error.kind === "api" && rules.error.status === 403 ? "forbidden" : "error"}
          types={[]}
          items={[]}
          canWrite={canWriteInventory(user.roles)}
          notice={notice}
        />
      );
    }
    sections.push({
      id: type.id,
      name: type.name,
      rules: rules.data.map((rule) => ({
        itemId: rule.item_id,
        itemName: rule.item_name,
        quantity: rule.quantity,
      })),
    });
  }
  return (
    <RulesScreen
      status="ready"
      types={sections}
      items={items.data.map((item) => ({ id: item.id, name: item.name }))}
      canWrite={canWriteInventory(user.roles)}
      notice={notice}
    />
  );
}

function ruleNotice(value: string | undefined): RulesNotice | null {
  if (value === "rule-saved" || value === "rule-removed") return value;
  return null;
}
