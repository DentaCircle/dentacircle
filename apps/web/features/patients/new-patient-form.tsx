"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fieldErrors, type PatientField } from "@/features/patients/field-errors";
import { parseErrorBody } from "@/lib/api/errors";

const SAVED_ID = /^P-\d{4,}$/;

export function NewPatientForm() {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [fieldMessage, setFieldMessage] = useState<Partial<Record<PatientField, string>>>({});
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setFieldMessage({});
    setFormMessage(null);

    const body: { full_name: string; phone: string; date_of_birth?: string } = {
      full_name: fullName,
      phone,
    };
    if (dateOfBirth !== "") body.date_of_birth = dateOfBirth;

    try {
      const response = await fetch("/api/patients", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(body),
      });
      if (response.ok) {
        const payload: unknown = await response.json();
        const displayId = readDisplayId(payload);
        if (displayId === null) {
          setFormMessage("The patient could not be saved.");
        } else {
          router.push(`/patients?created=${displayId}`);
          router.refresh();
          return;
        }
      } else {
        const error = parseErrorBody(response.status, await readJson(response));
        if (error.kind === "api" && error.status === 422) {
          const fields = fieldErrors(error.message);
          if (Object.keys(fields).length === 0) {
            setFormMessage("The patient could not be saved.");
          } else {
            setFieldMessage(fields);
          }
        } else if (error.kind === "api" && error.status === 403) {
          setFormMessage("You do not have access.");
        } else {
          setFormMessage("The patient could not be saved.");
        }
      }
    } catch {
      setFormMessage("Could not reach the server.");
    }

    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit}>
      <Field
        id="full_name"
        label="Name"
        value={fullName}
        message={fieldMessage.full_name}
        onChange={setFullName}
        autoComplete="name"
      />
      <Field
        id="phone"
        label="Phone"
        value={phone}
        message={fieldMessage.phone}
        onChange={setPhone}
        autoComplete="tel"
      />
      <Field
        id="date_of_birth"
        label="Date of birth (optional)"
        value={dateOfBirth}
        message={fieldMessage.date_of_birth}
        onChange={setDateOfBirth}
        type="date"
      />
      {formMessage === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {formMessage}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        Save patient
      </Button>
    </form>
  );
}

function Field({
  id,
  label,
  value,
  message,
  onChange,
  type = "text",
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  message: string | undefined;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
}) {
  const messageId = `${id}-error`;
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={id}
        type={type}
        autoComplete={autoComplete}
        value={value}
        aria-invalid={message !== undefined}
        aria-describedby={message === undefined ? undefined : messageId}
        onChange={(event) => onChange(event.target.value)}
      />
      {message === undefined ? null : (
        <p id={messageId} role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </div>
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function readDisplayId(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("display_id" in payload)) return null;
  const displayId = payload.display_id;
  if (typeof displayId !== "string" || !SAVED_ID.test(displayId)) return null;
  return displayId;
}
