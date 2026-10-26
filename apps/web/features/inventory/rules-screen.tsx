import Link from "next/link";

import {
  AddRuleForm,
  ChangeRuleForm,
  RemoveRuleForm,
  type RuleItemOption,
} from "@/features/inventory/rules-forms";

export type RuleRow = { itemId: string; itemName: string; quantity: number };

export type VisitTypeRules = {
  id: string;
  name: string;
  rules: RuleRow[];
};

export type RulesNotice = "rule-saved" | "rule-removed";

const NOTICES: Record<RulesNotice, string> = {
  "rule-saved": "Rule saved.",
  "rule-removed": "Rule removed.",
};

export type RulesScreenProps = {
  status: "ready" | "forbidden" | "error";
  types: VisitTypeRules[];
  items: RuleItemOption[];
  canWrite: boolean;
  notice: RulesNotice | null;
};

export function RulesScreen({ status, types, items, canWrite, notice }: RulesScreenProps) {
  return (
    <section className="flex flex-col gap-4">
      <p>
        <Link href="/inventory">Inventory</Link>
      </p>
      <h1 className="text-2xl font-semibold">Visit type rules</h1>
      {notice === null ? null : <p role="status">{NOTICES[notice]}</p>}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Visit type rules could not be loaded.</p> : null}
      {status === "ready" && types.length === 0 ? <p>No active visit types.</p> : null}
      {status === "ready"
        ? types.map((type) => (
            <section key={type.id} className="flex flex-col gap-3">
              <h2 className="text-lg font-medium">{type.name}</h2>
              {type.rules.length === 0 ? <p>No stock is used by this visit type.</p> : null}
              {type.rules.length === 0 ? null : (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="py-2 pr-3 font-medium" scope="col">
                        Item
                      </th>
                      <th className="py-2 font-medium" scope="col">
                        Quantity
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {type.rules.map((rule) => (
                      <tr key={rule.itemId} className="border-b">
                        <td className="py-2 pr-3">{rule.itemName}</td>
                        <td className="py-2">
                          {canWrite ? (
                            <div className="flex flex-wrap items-end gap-3">
                              <ChangeRuleForm
                                typeId={type.id}
                                itemId={rule.itemId}
                                itemName={rule.itemName}
                                quantity={rule.quantity}
                              />
                              <RemoveRuleForm
                                typeId={type.id}
                                itemId={rule.itemId}
                                itemName={rule.itemName}
                              />
                            </div>
                          ) : (
                            rule.quantity
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {canWrite ? (
                <AddRuleForm typeId={type.id} typeName={type.name} items={items} />
              ) : null}
            </section>
          ))
        : null}
    </section>
  );
}
