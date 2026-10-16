"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { careSessionHref } from "@/features/care-session/notices";
import { sessionFailure } from "@/features/care-session/outcomes";
import { recordCareSession, type CareSessionResult } from "@/lib/api/client";

export type OpenCareItem = {
  id: string;
  name: string;
  status: "planned" | "started";
};

export type OpenCarePlan = {
  id: string;
  title: string;
  items: OpenCareItem[];
};

type Choice = "no_change" | CareSessionResult;

export function SessionForm({
  appointmentId,
  plans,
}: {
  appointmentId: string;
  plans: OpenCarePlan[];
}) {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const chosen = plans.flatMap((plan) =>
    plan.items.flatMap((item) => {
      const choice = choices[item.id] ?? "no_change";
      if (choice === "no_change") return [];
      return [{ care_item_id: item.id, status: choice }];
    }),
  );

  async function onConfirm() {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);
    const result = await recordCareSession(appointmentId, chosen);
    if (result.ok) {
      router.push(careSessionHref(appointmentId, "saved"));
      router.refresh();
      return;
    }
    const failure = sessionFailure(result.error);
    if (failure.kind === "reload") {
      setChoices({});
      setIsConfirming(false);
      isSubmittingRef.current = false;
      setIsSubmitting(false);
      router.push(careSessionHref(appointmentId, failure.notice));
      router.refresh();
      return;
    }
    setMessage(failure.message);
    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setIsConfirming(true);
      }}
    >
      <p className="text-sm text-muted-foreground">Choose what was done today. No clinical notes.</p>
      {plans.map((plan) => (
        <section key={plan.id} className="flex flex-col gap-3">
          <h2 className="font-medium">{plan.title}</h2>
          {plan.items.map((item) => (
            <fieldset key={item.id} className="flex flex-col gap-1">
              <legend>{item.name}</legend>
              <Choice
                item={item}
                value={choices[item.id] ?? "no_change"}
                onChange={(value) => setChoices((current) => ({ ...current, [item.id]: value }))}
              />
            </fieldset>
          ))}
        </section>
      ))}
      {isConfirming ? (
        <div className="flex flex-wrap items-center gap-2">
          <p>Save care session? Completed items cannot be undone.</p>
          <Button type="button" onClick={onConfirm} disabled={isSubmitting}>
            Yes
          </Button>
          <Button type="button" variant="outline" onClick={() => setIsConfirming(false)}>
            Keep
          </Button>
        </div>
      ) : (
        <Button type="submit" disabled={chosen.length === 0}>
          Save care session
        </Button>
      )}
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
    </form>
  );
}

function Choice({
  item,
  value,
  onChange,
}: {
  item: OpenCareItem;
  value: Choice;
  onChange: (value: Choice) => void;
}) {
  const options: { value: Choice; label: string }[] = [
    { value: "no_change", label: "No change" },
    ...(item.status === "planned" ? [{ value: "started" as const, label: "Started" }] : []),
    { value: "completed", label: "Completed" },
  ];
  return (
    <div className="flex flex-wrap gap-3">
      {options.map((option) => (
        <label key={option.value} className="flex items-center gap-1 text-sm">
          <input
            type="radio"
            name={`care-item-${item.id}`}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
