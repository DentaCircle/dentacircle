"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inventoryItemHref } from "@/features/inventory/links";
import {
  CHOOSE_A_REASON,
  ENTER_A_CHANGE,
  ENTER_A_QUANTITY,
  NEGATIVE_CHANGE,
  inventoryFailure,
} from "@/features/inventory/notices";
import { adjustInventoryBatch, restockInventoryBatch } from "@/lib/api/client";

const REASONS = [
  { value: "damaged", label: "Damaged" },
  { value: "expired", label: "Expired" },
  { value: "correction", label: "Correction" },
] as const;

export function AddStockForm({ itemId, batchId }: { itemId: string; batchId: string }) {
  return (
    <StockForm
      idPrefix={`restock-${batchId}`}
      button="Add stock"
      fields={
        <QuantityField id={`restock-${batchId}-quantity`} label="Quantity" name="quantity" />
      }
      validate={(data) => {
        const quantity = String(data.get("quantity") ?? "").trim();
        if (!/^(?:[1-9]\d*)$/.test(quantity) || Number(quantity) > 1_000_000) {
          return { quantity: ENTER_A_QUANTITY };
        }
        return null;
      }}
      onSave={async (data) => {
        const quantity = String(data.get("quantity") ?? "").trim();
        const result = await restockInventoryBatch(batchId, quantity);
        if (!result.ok) return inventoryFailure(result.error);
        return "saved";
      }}
      afterSave={() => inventoryItemHref(itemId, "stock-added")}
    />
  );
}

export function AdjustForm({ itemId, batchId }: { itemId: string; batchId: string }) {
  return (
    <StockForm
      idPrefix={`adjust-${batchId}`}
      button="Adjust"
      fields={
        <>
          <QuantityField
            id={`adjust-${batchId}-change`}
            label="Quantity change"
            name="quantity_change"
          />
          <div className="flex flex-col gap-1">
            <Label htmlFor={`adjust-${batchId}-reason`}>Reason</Label>
            <select
              id={`adjust-${batchId}-reason`}
              name="reason"
              defaultValue=""
              className="h-9 rounded-md border bg-background px-2 text-sm"
            >
              <option value="">Choose a reason</option>
              {REASONS.map((reason) => (
                <option key={reason.value} value={reason.value}>
                  {reason.label}
                </option>
              ))}
            </select>
          </div>
        </>
      }
      validate={(data) => {
        const change = String(data.get("quantity_change") ?? "").trim();
        const reason = String(data.get("reason") ?? "");
        const errors: Record<string, string> = {};
        if (!/^-?(?:[1-9]\d*)$/.test(change) || Number(change.replace("-", "")) > 1_000_000) {
          errors.quantity_change = ENTER_A_CHANGE;
        }
        if (reason !== "damaged" && reason !== "expired" && reason !== "correction") {
          errors.reason = CHOOSE_A_REASON;
        } else if (
          (reason === "damaged" || reason === "expired") &&
          errors.quantity_change === undefined &&
          !change.startsWith("-")
        ) {
          errors.quantity_change = NEGATIVE_CHANGE;
        }
        return Object.keys(errors).length === 0 ? null : errors;
      }}
      onSave={async (data) => {
        const result = await adjustInventoryBatch(
          batchId,
          String(data.get("quantity_change") ?? "").trim(),
          String(data.get("reason") ?? ""),
        );
        if (!result.ok) return inventoryFailure(result.error);
        return "saved";
      }}
      afterSave={() => inventoryItemHref(itemId, "stock-adjusted")}
    />
  );
}

function QuantityField({ id, label, name }: { id: string; label: string; name: string }) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={name} inputMode="numeric" className="w-36" />
    </div>
  );
}

function StockForm({
  idPrefix,
  button,
  fields,
  validate,
  onSave,
  afterSave,
}: {
  idPrefix: string;
  button: string;
  fields: ReactNode;
  validate: (data: FormData) => Record<string, string> | null;
  onSave: (
    data: FormData,
  ) => Promise<"saved" | { form: string | null; fields: Record<string, string> }>;
  afterSave: () => string;
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
      form.reset();
      router.push(afterSave());
      router.refresh();
    } catch {
      setFormMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2" data-form={idPrefix}>
      {fields}
      <Button type="submit" disabled={isSubmitting}>
        {button}
      </Button>
      <FieldErrors errors={fieldErrors} />
      {formMessage === null ? null : <Alert text={formMessage} />}
    </form>
  );
}

function FieldErrors({ errors }: { errors: Record<string, string> }) {
  const messages = Object.values(errors);
  if (messages.length === 0) return null;
  return (
    <>
      {messages.map((message) => (
        <Alert key={message} text={message} />
      ))}
    </>
  );
}

function Alert({ text }: { text: string }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {text}
    </p>
  );
}
