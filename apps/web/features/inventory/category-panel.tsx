"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inventoryHref, type InventoryFilter } from "@/features/inventory/links";
import { ENTER_A_NAME, inventoryFailure, type InventoryNotice } from "@/features/inventory/notices";
import { createInventoryCategory, renameInventoryCategory } from "@/lib/api/client";

export type CategoryOption = { id: string; name: string; itemCount: number };

export function CategoryPanel({
  categories,
  filter,
  canWrite,
}: {
  categories: CategoryOption[];
  filter: InventoryFilter;
  canWrite: boolean;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-md border p-3">
      <h2 className="text-lg font-medium">Categories</h2>
      {categories.length === 0 ? <p>No categories yet.</p> : null}
      <ul className="flex flex-col gap-2">
        {categories.map((category) => (
          <li key={category.id} className="flex flex-wrap items-center gap-2">
            <span>
              {category.name} ({category.itemCount})
            </span>
            {canWrite ? <RenameCategory category={category} filter={filter} /> : null}
          </li>
        ))}
      </ul>
      {canWrite ? <AddCategory filter={filter} /> : null}
    </section>
  );
}

function AddCategory({ filter }: { filter: InventoryFilter }) {
  return (
    <NameForm
      idPrefix="add-category"
      label="New category"
      button="Add category"
      resetOnSave
      onSave={async (name) => {
        const result = await createInventoryCategory(name);
        if (!result.ok) return inventoryFailure(result.error).form ?? "Something went wrong.";
        return { notice: "category-added" };
      }}
      filter={filter}
    />
  );
}

function RenameCategory({
  category,
  filter,
}: {
  category: CategoryOption;
  filter: InventoryFilter;
}) {
  return (
    <NameForm
      idPrefix={`rename-${category.id}`}
      label={`Rename ${category.name}`}
      button="Rename"
      initial={category.name}
      onSave={async (name) => {
        const result = await renameInventoryCategory(category.id, name);
        if (!result.ok) return inventoryFailure(result.error).form ?? "Something went wrong.";
        return { notice: "category-renamed" };
      }}
      filter={filter}
    />
  );
}

function NameForm({
  idPrefix,
  label,
  button,
  initial = "",
  onSave,
  filter,
  resetOnSave = false,
}: {
  idPrefix: string;
  label: string;
  button: string;
  initial?: string;
  onSave: (name: string) => Promise<string | { notice: InventoryNotice }>;
  filter: InventoryFilter;
  resetOnSave?: boolean;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    const form = event.currentTarget;
    const name = String(new FormData(form).get("name") ?? "").trim();
    if (name === "") {
      setMessage(ENTER_A_NAME);
      return;
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const saved = await onSave(name);
      if (typeof saved === "string") {
        setMessage(saved);
        return;
      }
      if (resetOnSave) form.reset();
      router.push(inventoryHref(filter, 1, saved.notice));
      router.refresh();
    } catch {
      setMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${idPrefix}-name`}>{label}</Label>
        <Input
          id={`${idPrefix}-name`}
          name="name"
          defaultValue={initial}
          maxLength={80}
          aria-invalid={message !== null}
        />
      </div>
      <Button type="submit" disabled={isSubmitting}>
        {button}
      </Button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </form>
  );
}
