import { canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { canReadInventory } from "@/features/inventory/access";
import {
  getClinicDay, listAppointments, listClinicLabWork, listFollowUps, listRecalls,
  type CalendarVisit, type CurrentUser, type FollowUpQueuePage, type LabWorkPage,
  type RecallQueuePage,
} from "@/lib/api/client";

export type DashboardData = {
  mode: "coordination" | "inventory" | "restricted";
  today: string | null;
  timezone: string | null;
  appointments: CalendarVisit[] | null;
  followUps: FollowUpQueuePage | null;
  recalls: RecallQueuePage | null;
  lab: LabWorkPage | null;
};

export async function loadDashboard(user: CurrentUser, cookie: string): Promise<DashboardData> {
  const blank: DashboardData = {
    mode: "restricted", today: null, timezone: null,
    appointments: null, followUps: null, recalls: null, lab: null,
  };
  if (!canBookAppointments(user.roles)) {
    return { ...blank, mode: canReadInventory(user.roles) ? "inventory" : "restricted" };
  }
  const [day, followUps, recalls, lab] = await Promise.all([
    getClinicDay(cookie), listFollowUps(cookie, 1, "due"),
    listRecalls(cookie, 1, "due"), listClinicLabWork(cookie, "open", 1),
  ]);
  let today: string | null = null;
  if (day.ok) {
    try { today = clinicToday(day.data.timezone); } catch { /* Other sections remain usable. */ }
  }
  const appointments = today === null ? null : await listAppointments(cookie, today, today, null);
  return {
    mode: "coordination", today, timezone: today !== null && day.ok ? day.data.timezone : null,
    appointments: appointments?.ok ? appointments.data : null,
    followUps: followUps.ok ? followUps.data : null,
    recalls: recalls.ok ? recalls.data : null,
    lab: lab.ok ? lab.data : null,
  };
}
