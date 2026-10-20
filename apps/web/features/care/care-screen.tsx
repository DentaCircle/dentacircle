"use client";

import { Badge } from "@/components/ui/badge";
import { FollowUpForm } from "@/features/care/follow-up-form";
import { FollowUpLine } from "@/features/care/follow-up-line";
import { LabelForm } from "@/features/care/label-form";
import { CARE_NOTICES, type CareNotice } from "@/features/care/notices";
import { RenameItem } from "@/features/care/rename-item";
import { StatusButton } from "@/features/care/status-button";
import {
  addCareItem,
  createCarePlan,
  type CareItem,
  type CareItemStatus,
  type CarePlan,
  type FollowUp,
} from "@/lib/api/client";

export type FollowUpLoad =
  | { status: "hidden" }
  | { status: "ready"; followUp: FollowUp | null }
  | { status: "error" };

const STATUS_LABELS: Record<CareItemStatus, string> = {
  planned: "Planned",
  started: "Started",
  completed: "Completed",
  cancelled: "Cancelled",
};

export type CareScreenProps = {
  status: "ready" | "not-found" | "forbidden" | "error";
  patientId: string;
  plans: CarePlan[];
  canWrite: boolean;
  canCreateFollowUp: boolean;
  notice: CareNotice | null;
  followUp: FollowUpLoad;
};

export function CareScreen({
  status,
  patientId,
  plans,
  canWrite,
  canCreateFollowUp,
  notice,
  followUp,
}: CareScreenProps) {
  return (
    <section className="flex max-w-lg flex-col gap-6">
      <h1 className="text-2xl font-semibold">Care</h1>
      {notice === null ? null : <p role="status">{CARE_NOTICES[notice]}</p>}
      {followUp.status === "error" ? <p role="alert">Follow-up could not be loaded.</p> : null}
      {followUp.status === "ready" && followUp.followUp !== null ? (
        <FollowUpLine followUp={followUp.followUp} />
      ) : null}
      {status === "ready" &&
      followUp.status === "ready" &&
      followUp.followUp === null &&
      canCreateFollowUp ? (
        <FollowUpForm patientId={patientId} />
      ) : null}
      {status === "not-found" ? <p role="alert">Not found.</p> : null}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Care could not be loaded.</p> : null}
      {status === "ready" && plans.length === 0 ? <p>No care plans yet.</p> : null}
      {status === "ready"
        ? plans.map((plan) => (
            <Plan key={plan.id} plan={plan} patientId={patientId} canWrite={canWrite} />
          ))
        : null}
      {status === "ready" && canWrite ? (
        <LabelForm
          patientId={patientId}
          label="Title"
          button="New care plan"
          field="title"
          notice="plan_added"
          idSuffix={patientId}
          submit={(title) => createCarePlan(patientId, title)}
        />
      ) : null}
    </section>
  );
}

function Plan({ plan, patientId, canWrite }: { plan: CarePlan; patientId: string; canWrite: boolean }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{plan.title}</h2>
        <Badge variant="outline">{plan.is_open ? "Open" : "Finished"}</Badge>
      </div>
      {plan.items.length === 0 ? null : (
        <ul className="flex flex-col gap-3">
          {plan.items.map((item) => (
            <Item key={item.id} item={item} patientId={patientId} canWrite={canWrite} />
          ))}
        </ul>
      )}
      {canWrite ? (
        <LabelForm
          patientId={patientId}
          label="Service name"
          button="Add item"
          helper="Service name only. No clinical notes."
          field="name"
          notice="item_added"
          idSuffix={plan.id}
          submit={(name) => addCareItem(plan.id, name)}
        />
      ) : null}
    </section>
  );
}

function Item({ item, patientId, canWrite }: { item: CareItem; patientId: string; canWrite: boolean }) {
  const open = item.status === "planned" || item.status === "started";
  return (
    <li className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span>{item.name}</span>
        <Badge>{STATUS_LABELS[item.status]}</Badge>
      </div>
      {canWrite && open ? (
        <div className="flex flex-wrap items-center gap-2">
          {item.status === "planned" ? (
            <StatusButton patientId={patientId} itemId={item.id} target="started" />
          ) : null}
          <StatusButton patientId={patientId} itemId={item.id} target="completed" />
          <StatusButton patientId={patientId} itemId={item.id} target="cancelled" />
          <RenameItem patientId={patientId} itemId={item.id} />
        </div>
      ) : null}
    </li>
  );
}
