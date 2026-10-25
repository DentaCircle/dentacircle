"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inventoryItemHref } from "@/features/inventory/links";
import {
  CHECK_THE_DATE,
  ENTER_A_BATCH,
  ITEM_INACTIVE,
  inventoryFailure,
} from "@/features/inventory/notices";
import type { BatchRow } from "@/features/inventory/rows";
import {
  createInventoryBatch,
  setInventoryItemStatus,
  updateInventoryBatch,
  type ApiResult,
} from "@/lib/api/client";

export function ItemStatusButton({
  itemId,
  status,
}: {
  itemId: string;
  status: "active" | "inactive";
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const next = status === "active" ? "inactive" : "active";

  async function save() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const result = await setInventoryItemStatus(itemId, next);
      if (!result.ok) {
        setMessage(inventoryFailure(result.error).form);
        return;
      }
      setConfirming(false);
      router.push(inventoryItemHref(itemId, next === "inactive" ? "deactivated" : "reactivated"));
      router.refresh();
    } catch {
      setMessage("The change could not reach the server. Try again.");
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  if (status === "active" && !confirming) {
    return (
      <div className="flex flex-col gap-2">
        <Button type="button" variant="outline" onClick={() => setConfirming(true)}>
          Deactivate
        </Button>
        {message === null ? null : <Alert text={message} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Button type="button" disabled={isSubmitting} onClick={() => void save()}>
        {status === "active" ? "Confirm deactivation" : "Reactivate"}
      </Button>
      {message === null ? null : <Alert text={message} />}
    </div>
  );
}

export function AddBatchForm({ itemId, inactive }: { itemId: string; inactive: boolean }) {
  if (inactive) return <p>{ITEM_INACTIVE}</p>;
  return (
    <BatchFields
      idPrefix="add-batch"
      button="Add batch"
      batchNumber=""
      expiryOn=""
      resetOnSave
      onSave={(batchNumber, expiryOn) => createInventoryBatch(itemId, batchNumber, expiryOn)}
      afterSave={() => inventoryItemHref(itemId, "batch-added")}
    />
  );
}

export function EditBatchForm({ itemId, batch }: { itemId: string; batch: BatchRow }) {
  return (
    <BatchFields
      idPrefix={`batch-${batch.id}`}
      button="Save batch"
      batchNumber={batch.batchNumber}
      expiryOn={batch.expiryOn ?? ""}
      onSave={(batchNumber, expiryOn) => updateInventoryBatch(batch.id, batchNumber, expiryOn)}
      afterSave={() => inventoryItemHref(itemId, "batch-updated")}
    />
  );
}

function BatchFields({
  idPrefix,
  button,
  batchNumber,
  expiryOn,
  onSave,
  afterSave,
  resetOnSave = false,
}: {
  idPrefix: string;
  button: string;
  batchNumber: string;
  expiryOn: string;
  onSave: (batchNumber: string, expiryOn: string) => Promise<ApiResult<null>>;
  afterSave: () => string;
  resetOnSave?: boolean;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const number = String(data.get("batch_number") ?? "").trim();
    const expiry = String(data.get("expiry_on") ?? "");
    const local: Record<string, string> = {};
    if (number === "") local.batch_number = ENTER_A_BATCH;
    if (expiry !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(expiry)) local.expiry_on = CHECK_THE_DATE;
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
      const result = await onSave(number, expiry);
      if (!result.ok) {
        const failure = inventoryFailure(result.error);
        setFormMessage(failure.form);
        setFields(failure.fields);
        return;
      }
      if (resetOnSave) form.reset();
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
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${idPrefix}-number`}>Batch number</Label>
        <Input
          id={`${idPrefix}-number`}
          name="batch_number"
          defaultValue={batchNumber}
          maxLength={60}
          aria-invalid={fields.batch_number !== undefined}
        />
        <FieldError message={fields.batch_number} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${idPrefix}-expiry`}>Expiry date</Label>
        <Input
          id={`${idPrefix}-expiry`}
          name="expiry_on"
          type="date"
          defaultValue={expiryOn}
          aria-invalid={fields.expiry_on !== undefined}
        />
        <FieldError message={fields.expiry_on} />
      </div>
      <Button type="submit" disabled={isSubmitting}>
        {button}
      </Button>
      {formMessage === null ? null : <Alert text={formMessage} />}
    </form>
  );
}

function Alert({ text }: { text: string }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {text}
    </p>
  );
}

function FieldError({ message }: { message: string | undefined }) {
  if (message === undefined) return null;
  return <Alert text={message} />;
}
