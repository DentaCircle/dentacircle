"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CategoryOption } from "@/features/inventory/category-panel";
import { inventoryHref, inventoryItemHref, type InventoryFilter } from "@/features/inventory/links";
import {
  CHECK_THE_THRESHOLD,
  CHOOSE_A_CATEGORY,
  ENTER_A_NAME,
  ENTER_A_UNIT,
  inventoryFailure,
} from "@/features/inventory/notices";
import { createInventoryItem, updateInventoryItem } from "@/lib/api/client";

type ItemFields = {
  name: string;
  categoryId: string;
  unit: string;
  threshold: string;
};

export function AddItemForm({
  categories,
  filter,
}: {
  categories: CategoryOption[];
  filter: InventoryFilter;
}) {
  if (categories.length === 0) {
    return <p>Add a category first.</p>;
  }
  return (
    <ItemFieldsForm
      idPrefix="add-item"
      button="Add item"
      categories={categories}
      initial={{ name: "", categoryId: "", unit: "", threshold: "0" }}
      onSave={async (fields) => {
        const result = await createInventoryItem({
          name: fields.name,
          categoryId: fields.categoryId,
          unit: fields.unit,
          lowStockThreshold: fields.threshold,
        });
        if (!result.ok) return inventoryFailure(result.error);
        return "saved";
      }}
      afterSave={() => inventoryHref(filter, 1, "item-added")}
    />
  );
}

export function EditItemForm({
  itemId,
  categories,
  initial,
}: {
  itemId: string;
  categories: CategoryOption[];
  initial: ItemFields;
}) {
  return (
    <ItemFieldsForm
      idPrefix="edit-item"
      button="Save item"
      categories={categories}
      initial={initial}
      onSave={async (fields) => {
        const result = await updateInventoryItem(itemId, {
          name: fields.name,
          categoryId: fields.categoryId,
          unit: fields.unit,
          lowStockThreshold: fields.threshold,
        });
        if (!result.ok) return inventoryFailure(result.error);
        return "saved";
      }}
      afterSave={() => inventoryItemHref(itemId, "item-updated")}
    />
  );
}

function ItemFieldsForm({
  idPrefix,
  button,
  categories,
  initial,
  onSave,
  afterSave,
}: {
  idPrefix: string;
  button: string;
  categories: CategoryOption[];
  initial: ItemFields;
  onSave: (fields: ItemFields) => Promise<"saved" | { form: string | null; fields: Record<string, string> }>;
  afterSave: () => string;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    const data = new FormData(event.currentTarget);
    const next: ItemFields = {
      name: String(data.get("name") ?? "").trim(),
      categoryId: String(data.get("category_id") ?? ""),
      unit: String(data.get("unit") ?? "").trim(),
      threshold: String(data.get("low_stock_threshold") ?? "").trim(),
    };
    const local = localFieldErrors(next);
    if (Object.keys(local).length > 0) {
      setFields(local);
      setFormMessage(null);
      return;
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setFormMessage(null);
    setFields({});
    try {
      const saved = await onSave(next);
      if (saved !== "saved") {
        setFormMessage(saved.form);
        setFields(saved.fields);
        return;
      }
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
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <Field id={`${idPrefix}-name`} label="Name" name="name" defaultValue={initial.name} error={fields.name} />
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${idPrefix}-category`}>Category</Label>
        <select
          id={`${idPrefix}-category`}
          name="category_id"
          defaultValue={initial.categoryId}
          className="h-9 rounded-md border bg-transparent px-2 text-sm"
          aria-invalid={fields.category_id !== undefined}
        >
          <option value="">Choose a category</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
        <FieldError message={fields.category_id} />
      </div>
      <Field id={`${idPrefix}-unit`} label="Unit" name="unit" defaultValue={initial.unit} error={fields.unit} />
      <Field
        id={`${idPrefix}-threshold`}
        label="Low stock threshold"
        name="low_stock_threshold"
        defaultValue={initial.threshold}
        error={fields.low_stock_threshold}
      />
      <Button type="submit" disabled={isSubmitting}>
        {button}
      </Button>
      {formMessage === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {formMessage}
        </p>
      )}
    </form>
  );
}

function Field({
  id,
  label,
  name,
  defaultValue,
  error,
}: {
  id: string;
  label: string;
  name: string;
  defaultValue: string;
  error: string | undefined;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={name} defaultValue={defaultValue} aria-invalid={error !== undefined} />
      <FieldError message={error} />
    </div>
  );
}

function FieldError({ message }: { message: string | undefined }) {
  if (message === undefined) return null;
  return (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  );
}

function localFieldErrors(fields: ItemFields): Record<string, string> {
  const errors: Record<string, string> = {};
  if (fields.name === "") errors.name = ENTER_A_NAME;
  if (fields.categoryId === "") errors.category_id = CHOOSE_A_CATEGORY;
  if (fields.unit === "") errors.unit = ENTER_A_UNIT;
  if (!/^(0|[1-9]\d*)$/.test(fields.threshold) || Number(fields.threshold) > 1_000_000) {
    errors.low_stock_threshold = CHECK_THE_THRESHOLD;
  }
  return errors;
}
