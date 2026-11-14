import { beforeEach, expect, test, vi } from "vitest";
import { loadDashboard } from "@/features/dashboard/load-dashboard";
import * as api from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({ getClinicDay: vi.fn(), listAppointments: vi.fn(), listFollowUps: vi.fn(), listRecalls: vi.fn(), listClinicLabWork: vi.fn(), listReminderTotal: vi.fn(), listInventoryItems: vi.fn() }));
const user: api.CurrentUser = { id: "synthetic-user", full_name: "Synthetic User", email: "synthetic@x.test", roles: ["receptionist"], clinic: { id: "synthetic-clinic", name: "Synthetic Clinic" } };
const emptyPage = { items: [], total: 0, page: 1, page_size: 20 };
const failure = { ok: false, error: { kind: "network", message: "Unavailable" } } as const;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  vi.mocked(api.listInventoryItems).mockResolvedValue({ ok: true, data: { ...emptyPage, total: 42 } });
  vi.mocked(api.getClinicDay).mockResolvedValue({ ok: true, data: { timezone: "Asia/Kolkata" } });
  vi.mocked(api.listAppointments).mockResolvedValue({ ok: true, data: [] });
  vi.mocked(api.listFollowUps).mockResolvedValue({ ok: true, data: { ...emptyPage, total: 42 } });
  vi.mocked(api.listRecalls).mockResolvedValue({ ok: true, data: { ...emptyPage, total: 31 } });
  vi.mocked(api.listClinicLabWork).mockResolvedValue({ ok: true, data: { ...emptyPage, total: 27 } });
  vi.mocked(api.listReminderTotal).mockResolvedValue({ ok: true, data: { total: 53 } });
});

test("uses clinic-local day at the UTC boundary and API totals beyond a page", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-25T21:00:00Z"));
  const data = await loadDashboard(user, "dc_session=synthetic");
  expect(data.today).toBe("2026-10-26");
  expect(api.listAppointments).toHaveBeenCalledWith("dc_session=synthetic", "2026-10-26", "2026-10-26", null);
  expect(api.listFollowUps).toHaveBeenCalledWith("dc_session=synthetic", 1, "due");
  expect(api.listRecalls).toHaveBeenCalledWith("dc_session=synthetic", 1, "due");
  expect(api.listClinicLabWork).toHaveBeenCalledWith("dc_session=synthetic", "open", 1);
  expect(data.followUps?.total).toBe(42);
  expect(data.recalls?.total).toBe(31);
  expect(data.lab?.total).toBe(27);
  expect(data.reminders?.total).toBe(53);
  expect(api.listReminderTotal).toHaveBeenCalledWith("dc_session=synthetic");
  vi.useRealTimers();
});

test.each(["inventory_admin", "unknown"])("%s makes no patient or calendar requests", async (role) => {
  const data = await loadDashboard({ ...user, roles: [role] }, "synthetic");
  expect(data.mode).toBe(role === "inventory_admin" ? "inventory" : "restricted");
  expect(api.listAppointments).not.toHaveBeenCalled();
  expect(api.listFollowUps).not.toHaveBeenCalled();
  expect(api.listInventoryItems).toHaveBeenCalledTimes(role === "inventory_admin" ? 4 : 0);
});

test.each(["clinician", "clinic_admin"])("%s retains the existing coordination access", async (role) => {
  expect((await loadDashboard({ ...user, roles: [role] }, "synthetic")).mode).toBe("coordination");
  expect(api.listFollowUps).toHaveBeenCalled();
});

test("a queue failure preserves other sections and is not returned as zero", async () => {
  vi.mocked(api.listFollowUps).mockResolvedValue(failure);
  const data = await loadDashboard(user, "synthetic");
  expect(data.followUps).toBeNull();
  expect(data.recalls?.total).toBe(31);
  expect(data.appointments).toEqual([]);
});

test.each(["failure", "invalid timezone"])("clinic day %s does not fetch the wrong day's appointments", async (scenario) => {
  vi.mocked(api.getClinicDay).mockResolvedValue(scenario === "failure" ? failure : { ok: true, data: { timezone: "Synthetic/Invalid" } });
  const data = await loadDashboard(user, "synthetic");
  expect(data.today).toBeNull();
  expect(data.appointments).toBeNull();
  expect(api.listAppointments).not.toHaveBeenCalled();
  expect(data.followUps?.total).toBe(42);
});

test("appointment and remaining queue failures remain independently unavailable", async () => {
  vi.mocked(api.listAppointments).mockResolvedValue(failure);
  vi.mocked(api.listRecalls).mockResolvedValue(failure);
  vi.mocked(api.listClinicLabWork).mockResolvedValue(failure);
  const data = await loadDashboard(user, "synthetic");
  expect(data.appointments).toBeNull();
  expect(data.recalls).toBeNull();
  expect(data.lab).toBeNull();
  expect(data.followUps?.total).toBe(42);
});

 test("mixed inventory and coordination roles receive coordination data", async () => {
  const data = await loadDashboard({ ...user, roles: ["inventory_admin", "receptionist"] }, "synthetic");
  expect(data.mode).toBe("coordination");
  expect(api.listReminderTotal).toHaveBeenCalled();
});

test("a reminder failure leaves the other totals available", async () => {
  vi.mocked(api.listReminderTotal).mockResolvedValue(failure);
  const data = await loadDashboard(user, "synthetic");
  expect(data.reminders).toBeNull();
  expect(data.followUps?.total).toBe(42);
});


test.each([{ roles: ["inventory_admin"] }, { roles: ["clinician"] }, { roles: ["clinic_admin"] }, { roles: ["receptionist", "inventory_admin"] }])("inventory roles $roles load filtered totals", async ({ roles }) => {
  const result = await loadDashboard({ ...user, roles }, "synthetic");
  for (const alert of ["out_of_stock", "low_stock", "expiring_soon", "expired"]) {
    expect(api.listInventoryItems).toHaveBeenCalledWith("synthetic", "active", "", "", 1, 1, alert);
  }
  expect(result.inventory?.out_of_stock).toBe(42);
});

test("inventory failures remain independent and refresh loads again", async () => {
  vi.mocked(api.listInventoryItems).mockResolvedValueOnce(failure);
  vi.mocked(api.getClinicDay).mockResolvedValue(failure);
  const first = await loadDashboard({ ...user, roles: ["clinician"] }, "synthetic");
  expect(first.inventory?.out_of_stock).toBeNull();
  expect(first.inventory?.low_stock).toBe(42);
  const second = await loadDashboard({ ...user, roles: ["clinician"] }, "synthetic");
  expect(second.inventory?.out_of_stock).toBe(42);
  expect(api.listInventoryItems).toHaveBeenCalledTimes(8);
});

test("receptionist never loads inventory", async () => {
  expect((await loadDashboard(user, "synthetic")).inventory).toBeNull();
  expect(api.listInventoryItems).not.toHaveBeenCalled();
});
