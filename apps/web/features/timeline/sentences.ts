import { formatDueOn } from "@/features/care/follow-up-line";
import type {
  TimelineCareItemSubject,
  TimelineFollowUpSubject,
  TimelineDocumentSubject,
  TimelineItem,
  TimelineRecallSubject,
  TimelineSessionSubject,
  TimelineVisitSubject,
} from "@/lib/api/client";

const VISIT_LEAD: Record<string, string> = {
  visit_booked: "Visit booked",
  visit_rescheduled: "Visit rescheduled",
  visit_cancelled: "Visit cancelled",
  visit_arrived: "Visit arrived",
  visit_started: "Visit started",
  visit_completed: "Visit completed",
  visit_no_show: "Visit no-show",
};

const CARE_ITEM_LEAD: Record<string, string> = {
  care_item_added: "Care item added",
  care_item_started: "Care item started",
  care_item_completed: "Care item completed",
  care_item_cancelled: "Care item cancelled",
};

const FOLLOW_UP_LEAD: Record<string, string> = {
  follow_up_created: "Follow-up created",
  follow_up_updated: "Follow-up updated",
  follow_up_contacted: "Follow-up contacted",
  follow_up_booked: "Follow-up booked",
  follow_up_completed: "Follow-up completed",
  follow_up_released: "Follow-up released",
  follow_up_cancelled: "Follow-up cancelled",
};

const RECALL_LEAD: Record<string, string> = {
  recall_created: "Recall created",
  recall_updated: "Recall updated",
  recall_contacted: "Recall contacted",
  recall_booked: "Recall booked",
  recall_completed: "Recall completed",
  recall_released: "Recall released",
  recall_cancelled: "Recall cancelled",
};

export function entrySentence(item: TimelineItem): string {
  if (item.kind === "patient_registered") return "Patient registered";
  if (item.kind === "document_uploaded" && isDocument(item.subject)) {
    return `Document uploaded: ${item.subject.filename}`;
  }
  const visitLead = VISIT_LEAD[item.kind];
  if (visitLead !== undefined && isVisit(item.subject)) {
    return `${visitLead}: ${item.subject.type_name} with ${item.subject.clinician_name}`;
  }
  const careLead = CARE_ITEM_LEAD[item.kind];
  if (careLead !== undefined && isCareItem(item.subject)) {
    return `${careLead}: ${item.subject.name}`;
  }
  if (item.kind === "care_session_recorded" && isSession(item.subject)) {
    return `Care recorded: ${item.subject.item_names.join(", ")}`;
  }
  const followUpLead = FOLLOW_UP_LEAD[item.kind];
  if (followUpLead !== undefined && isFollowUp(item.subject)) {
    return `${followUpLead}, due ${formatDueOn(item.subject.due_on)}`;
  }
  const recallLead = RECALL_LEAD[item.kind];
  if (recallLead !== undefined && isRecall(item.subject)) {
    return `${recallLead}: ${item.subject.type_name}, due ${formatDueOn(item.subject.due_on)}`;
  }
  return item.kind;
}

function isDocument(subject: TimelineItem["subject"]): subject is TimelineDocumentSubject {
  return subject !== null && "document_id" in subject && "filename" in subject;
}

function isVisit(subject: TimelineItem["subject"]): subject is TimelineVisitSubject {
  return subject !== null && "appointment_id" in subject;
}

function isCareItem(subject: TimelineItem["subject"]): subject is TimelineCareItemSubject {
  return subject !== null && "name" in subject && !("care_session_id" in subject);
}

function isSession(subject: TimelineItem["subject"]): subject is TimelineSessionSubject {
  return subject !== null && "care_session_id" in subject;
}

function isFollowUp(subject: TimelineItem["subject"]): subject is TimelineFollowUpSubject {
  return subject !== null && "due_on" in subject && !("type_name" in subject);
}

function isRecall(subject: TimelineItem["subject"]): subject is TimelineRecallSubject {
  return subject !== null && "due_on" in subject && "type_name" in subject;
}
