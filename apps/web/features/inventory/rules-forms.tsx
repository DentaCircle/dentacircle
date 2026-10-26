"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiError } from "@/lib/api/errors";
import { removeResourceRule, saveResourceRule } from "@/lib/api/client";

export const ENTER_A_RULE_QUANTITY = "Enter a whole number from 1 to 1,000.";
export const RULE_NOT_FOUND = "Not found.";
export const RULE_INACTIVE = "This item is inactive.";

export type RuleItemOption = { id: string; name: string };

export function AddRuleForm({
  typeId,
  typeName,
  items,
}: {
  typeId: string;
  typeName: string;
  items: RuleItemOption[];
}) {
  return (
    <RuleForm
      label={`Add a rule for ${typeName}`}
      button="Add rule"
      afterSave="/inventory/rules?notice=rule-saved"
      fields={
        <>
          <div className="flex flex-col gap-1">
            <Label htmlFor={`add-${typeId}-item`}>Item</Label>
            <select
              id={`add-${typeId}-item`}
              name="item_id"
              defaultValue=""
              className="h-9 rounded-md border bg-background px-2 text-sm"
            >
              <option value="">Choose an item</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <QuantityField id={`add-${typeId}-quantity`} />
        </>
      }
      validate={(data) => {
        const fields: Record<string, string> = {};
        if (String(data.get("item_id") ?? "") === "") fields.item_id = "Choose an item.";
        const quantity = ruleQuantityError(String(data.get("quantity") ?? "").trim());
        if (quantity !== null) fields.quantity = quantity;
        return Object.keys(fields).length === 0 ? null : fields;
      }}
      onSave={async (data) => {
        const result = await saveResourceRule(
          typeId,
          String(data.get("item_id") ?? ""),
          String(data.get("quantity") ?? "").trim(),
        );
        if (!result.ok) return ruleFailure(result.error);
        return "saved";
      }}
    />
  );
}

export function ChangeRuleForm({
  typeId,
  itemId,
  itemName,
  quantity,
}: {
  typeId: string;
  itemId: string;
  itemName: string;
  quantity: number;
}) {
  return (
    <RuleForm
      label={`Change ${itemName}`}
      button="Save"
      afterSave="/inventory/rules?notice=rule-saved"
      fields={<QuantityField id={`change-${typeId}-${itemId}`} defaultValue={String(quantity)} />}
      validate={(data) => {
        const message = ruleQuantityError(String(data.get("quantity") ?? "").trim());
        return message === null ? null : { quantity: message };
      }}
      onSave={async (data) => {
        const result = await saveResourceRule(
          typeId,
          itemId,
          String(data.get("quantity") ?? "").trim(),
        );
        if (!result.ok) return ruleFailure(result.error);
        return "saved";
      }}
    />
  );
}

export function RemoveRuleForm({
  typeId,
  itemId,
  itemName,
}: {
  typeId: string;
  itemId: string;
  itemName: string;
}) {
  return (
    <RuleForm
      label={`Remove ${itemName}`}
      button="Remove"
      afterSave="/inventory/rules?notice=rule-removed"
      fields={null}
      validate={() => null}
      onSave={async () => {
        const result = await removeResourceRule(typeId, itemId);
        if (!result.ok) return ruleFailure(result.error);
        return "saved";
      }}
    />
  );
}

function QuantityField({ id, defaultValue }: { id: string; defaultValue?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>Quantity</Label>
      <Input
        id={id}
        name="quantity"
        inputMode="numeric"
        defaultValue={defaultValue}
        className="w-28"
      />
    </div>
  );
}

function RuleForm({
  label,
  button,
  fields,
  validate,
  onSave,
  afterSave,
}: {
  label: string;
  button: string;
  fields: ReactNode;
  validate: (data: FormData) => Record<string, string> | null;
  onSave: (data: FormData) => Promise<"saved" | { form: string | null; fields: Record<string, string> }>;
  afterSave: string;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const local = validate(data);
    if (local !== null) {
      setFieldErrors(local);
      setFormMessage(null);
      return;
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setFormMessage(null);
    setFieldErrors({});
    try {
      const result = await onSave(data);
      if (result !== "saved") {
        setFormMessage(result.form);
        setFieldErrors(result.fields);
        return;
      }
      router.push(afterSave);
      router.refresh();
    } catch {
      setFormMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} aria-label={label} className="flex flex-wrap items-end gap-2">
      {fields}
      <Button type="submit" disabled={isSubmitting}>
        {button}
      </Button>
      {Object.values(fieldErrors).map((message) => (
        <p key={message} role="alert" className="text-sm text-destructive">
          {message}
        </p>
      ))}
      {formMessage === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {formMessage}
        </p>
      )}
    </form>
  );
}

function ruleQuantityError(value: string): string | null {
  if (!/^[1-9]\d*$/.test(value)) return ENTER_A_RULE_QUANTITY;
  if (Number(value) > 1000) return ENTER_A_RULE_QUANTITY;
  return null;
}

function ruleFailure(error: ApiError): { form: string | null; fields: Record<string, string> } {
  if (error.kind === "timeout") return { form: "The change took too long. Try again.", fields: {} };
  if (error.kind === "network") {
    return { form: "The change could not reach the server. Try again.", fields: {} };
  }
  if (error.status === 404) return { form: RULE_NOT_FOUND, fields: {} };
  if (error.status === 409) return { form: RULE_INACTIVE, fields: {} };
  if (error.status === 403) return { form: "You do not have access.", fields: {} };
  if (error.status === 422 && error.message.includes("quantity")) {
    return { form: null, fields: { quantity: ENTER_A_RULE_QUANTITY } };
  }
  if (error.status === 422) return { form: "Check the form.", fields: {} };
  return { form: "Something went wrong.", fields: {} };
}
