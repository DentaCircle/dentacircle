import { canBookAppointments } from "@/features/appointments/access";
import { clinicToday } from "@/features/appointments/wall-time";
import { canReadInventory } from "@/features/inventory/access";
import {
  getClinicDay, listAppointments, listClinicLabWork, listFollowUps, listRecalls, listReminderTotal, listInventoryItems,
  type CalendarVisit, type CurrentUser, type FollowUpQueuePage, type LabWorkPage,
  type RecallQueuePage, type ReminderTotal,
} from "@/lib/api/client";

export const inventoryAlerts = ["out_of_stock", "low_stock", "expiring_soon", "expired"] as const;
export type InventoryCounts = Record<(typeof inventoryAlerts)[number], number | null>;

export type DashboardData = {
  inventory: InventoryCounts | null;
  mode: "coordination" | "inventory" | "restricted";
  today: string | null;
  timezone: string | null;
  appointments: CalendarVisit[] | null;
  followUps: FollowUpQueuePage | null;
  recalls: RecallQueuePage | null;
  lab: LabWorkPage | null;
  reminders: ReminderTotal | null;
};

export async function loadDashboard(user: CurrentUser, cookie: string): Promise<DashboardData> {
  const blank: DashboardData = {
    inventory: null, mode: "restricted", today: null, timezone: null,
    appointments: null, followUps: null, recalls: null, lab: null, reminders: null,
  };
  const inventoryPromise = canReadInventory(user.roles) ? loadInventory(cookie) : Promise.resolve(null);
  if (!canBookAppointments(user.roles)) {
    return { ...blank, inventory: await inventoryPromise, mode: canReadInventory(user.roles) ? "inventory" : "restricted" };
  }
  const [day, followUps, recalls, lab, reminders] = await Promise.all([
    getClinicDay(cookie), listFollowUps(cookie, 1, "due"),
    listRecalls(cookie, 1, "due"), listClinicLabWork(cookie, "open", 1), listReminderTotal(cookie),
  ]);
  let today: string | null = null;
  if (day.ok) {
    try { today = clinicToday(day.data.timezone); } catch { /* Other sections remain usable. */ }
  }
  const appointments = today === null ? null : await listAppointments(cookie, today, today, null);
  return {
    inventory: await inventoryPromise, mode: "coordination", today, timezone: today !== null && day.ok ? day.data.timezone : null,
    appointments: appointments?.ok ? appointments.data : null,
    followUps: followUps.ok ? followUps.data : null,
    recalls: recalls.ok ? recalls.data : null,
    lab: lab.ok ? lab.data : null,
    reminders: reminders.ok ? reminders.data : null,
  };
}

async function loadInventory(cookie: string): Promise<InventoryCounts> {
  const [outOfStock, lowStock, expiringSoon, expired] = await Promise.all(
    inventoryAlerts.map((alert) => listInventoryItems(cookie, "active", "", "", 1, 1, alert)),
  );
  return {
    out_of_stock: outOfStock.ok ? outOfStock.data.total : null,
    low_stock: lowStock.ok ? lowStock.data.total : null,
    expiring_soon: expiringSoon.ok ? expiringSoon.data.total : null,
    expired: expired.ok ? expired.data.total : null,
  };
}
