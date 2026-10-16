"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { careHref, type CareNotice } from "@/features/care/notices";
import { careFailure } from "@/features/care/outcomes";
import type { ApiResult } from "@/lib/api/errors";

export function LabelForm({
  patientId,
  label,
  button,
  helper,
  field,
  notice,
  idSuffix,
  submit,
}: {
  patientId: string;
  label: string;
  button: string;
  helper?: string;
  field: "title" | "name";
  notice: CareNotice;
  idSuffix: string;
  submit: (value: string) => Promise<ApiResult<null>>;
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [value, setValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldMessage, setFieldMessage] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setFieldMessage(null);
    setFormMessage(null);
    const result = await submit(value);
    if (result.ok) {
      setValue("");
      isSubmittingRef.current = false;
      setIsSubmitting(false);
      router.push(careHref(patientId, notice));
      router.refresh();
      return;
    }
    const failure = careFailure(result.error, field);
    if (failure.kind === "reload") {
      router.push(careHref(patientId, failure.notice));
      router.refresh();
      return;
    }
    if (failure.kind === "field") setFieldMessage(failure.message);
    else setFormMessage(failure.message);
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2">
      <Label htmlFor={`${field}-${idSuffix}`}>{label}</Label>
      <Input
        id={`${field}-${idSuffix}`}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        aria-invalid={fieldMessage !== null}
      />
      {helper === undefined ? null : <p className="text-sm text-muted-foreground">{helper}</p>}
      {fieldMessage === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {fieldMessage}
        </p>
      )}
      <div>
        <Button type="submit" disabled={isSubmitting}>
          {button}
        </Button>
      </div>
      {formMessage === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {formMessage}
        </p>
      )}
    </form>
  );
}
