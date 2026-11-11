import Link from "next/link";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { ReminderActions } from "@/features/reminders/actions";
import { apiBaseUrl, getClinicDay } from "@/lib/api/client";

export const dynamic = "force-dynamic";
type Item = { id: string; appointment_id: string; due_at: string; starts_at: string; patient_id: string; patient_name: string };
type Data = { items: Item[]; total: number; page: number; page_size: number };

export default async function RemindersPage({ searchParams }: { searchParams: Promise<{ view?: string; page?: string }> }) {
  const user = await requireUser();
  if (!user.roles.some((role) => ["receptionist", "clinician", "clinic_admin"].includes(role))) return <p role="alert">You do not have access.</p>;
  const params = await searchParams;
  const view = params.view === "pending" ? "pending" : "due";
  const parsed = Number(params.page ?? "1");
  const page = Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1;
  const cookie = await sessionCookieHeader();
  let data: Data;
  let zone: string;
  try {
    const [response, clinic] = await Promise.all([fetch(`${apiBaseUrl()}/reminders?view=${view}&page=${page}`, { headers: { cookie }, cache: "no-store" }), getClinicDay(cookie)]);
    if (response.status === 403) return <p role="alert">You do not have access.</p>;
    if (!response.ok || !clinic.ok) throw new Error("load failed");
    data = await response.json() as Data;
    if (!Array.isArray(data.items) || typeof data.total !== "number") throw new Error("invalid response");
    zone = clinic.data.timezone;
  } catch { return <section><h1>Reminders</h1><p role="alert">Reminders could not be loaded.</p></section>; }
  const date = (value: string) => new Intl.DateTimeFormat("en-IN", { timeZone: zone, dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  const day = (value: string) => new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  return <section className="flex flex-col gap-4"><h1 className="text-2xl font-semibold">Reminders</h1>
    <nav aria-label="View" className="flex gap-3"><Link href="/reminders?view=due" aria-current={view === "due" ? "page" : undefined}>Due</Link><Link href="/reminders?view=pending" aria-current={view === "pending" ? "page" : undefined}>All pending</Link></nav>
    {data.total === 0 ? <p>{view === "due" ? "No reminders are due." : "No pending reminders."}</p> : <ul>{data.items.map((item) => <li key={item.id} className="border-b py-4 flex flex-wrap justify-between gap-3"><div><Link className="underline" href={`/patients/${item.patient_id}`}>{item.patient_name}</Link><p>Due {date(item.due_at)}</p><Link className="underline" href={`/calendar?view=day&date=${day(item.starts_at)}`}>Visit {date(item.starts_at)}</Link></div><ReminderActions id={item.id} /></li>)}</ul>}
    <nav aria-label="Pages" className="flex gap-3">{page > 1 ? <Link href={`/reminders?view=${view}&page=${page - 1}`}>Previous</Link> : null}{page * 20 < data.total ? <Link href={`/reminders?view=${view}&page=${page + 1}`}>Next</Link> : null}</nav>
  </section>;
}
