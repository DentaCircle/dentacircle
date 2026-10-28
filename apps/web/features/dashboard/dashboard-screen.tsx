import Link from "next/link";
import {
  ArrowDownLeft, ArrowRight, CalendarDays, Check, ChevronRight, Clock3,
  FlaskConical, Layers3, Package, PhoneCall, Plus, RotateCcw, Search,
  ShieldCheck, Sparkles, Users, type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { wallTime } from "@/features/appointments/wall-time";
import type { DashboardData } from "@/features/dashboard/load-dashboard";
import type { CalendarVisit, CurrentUser } from "@/lib/api/client";

type DashboardProps = { user: CurrentUser; data: DashboardData };
type AgendaProps = { visits: CalendarVisit[] | null; href: string };

export function DashboardScreen({ user, data }: DashboardProps) {
  return (
    <section className="dashboard space-y-7">
      <DashboardHeading user={user} coordination={data.mode === "coordination"} />
      {data.mode === "coordination" ? (
        <CoordinationDashboard data={data} />
      ) : (
        <OtherDashboard mode={data.mode} />
      )}
      <footer className="dashboard-footer">
        <span className="flex items-center gap-1.5">
          <ShieldCheck size={14} aria-hidden="true" />
          Connected care starts with a coordinated team.
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <span>{user.clinic.name}</span>
          <span aria-hidden="true">·</span>
          <ul aria-label="Roles" className="flex flex-wrap gap-2">
            {user.roles.map((role) => (
              <li key={role} className="capitalize">{role.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </div>
      </footer>
    </section>
  );
}

function DashboardHeading({ user, coordination }: { user: CurrentUser; coordination: boolean }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow mb-2">YOUR CLINIC AT A GLANCE</p>
        <h1 className="dashboard-title">Dashboard<span className="title-dot">.</span></h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Welcome back, <span className="font-medium text-foreground">{user.full_name}</span>.
          Let’s make room for better care.
        </p>
      </div>
      {coordination ? (
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="h-10 bg-white px-4">
            <Link href="/patients"><Search aria-hidden="true" />Find patient</Link>
          </Button>
          <Button asChild className="h-10 px-4 shadow-sm">
            <Link href="/patients/new"><Plus aria-hidden="true" />Register patient</Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function CoordinationDashboard({ data }: { data: DashboardData }) {
  const calendarHref = data.today === null ? "/calendar" : `/calendar?date=${data.today}`;
  return (
    <>
      <DailyBrief data={data} calendarHref={calendarHref} />
      <div className="metric-grid">
        <Metric label="Appointments today" value={data.appointments?.length ?? null}
          description="Your daily schedule" href={calendarHref} icon={CalendarDays} tone="teal" />
        <Metric label="Follow-ups due" value={data.followUps?.total ?? null}
          description="Due today & overdue" href="/follow-ups" icon={PhoneCall} tone="amber" />
        <Metric label="Recalls due" value={data.recalls?.total ?? null}
          description="Time to reconnect" href="/recalls" icon={RotateCcw} tone="violet" />
        <Metric label="Open lab work" value={data.lab?.total ?? null}
          description="Pending & ready to collect" href="/lab" icon={FlaskConical} tone="blue" />
      </div>
      <div className="dashboard-columns">
        <div className="min-w-0 space-y-6">
          <Agenda visits={data.appointments} href={calendarHref} />
          <DayProgress visits={data.appointments} href={calendarHref} />
        </div>
        <div className="min-w-0 space-y-6">
          <Attention data={data} />
          <QuickActions />
        </div>
      </div>
    </>
  );
}

function DailyBrief({ data, calendarHref }: { data: DashboardData; calendarHref: string }) {
  return (
    <div className="overview-banner">
      <div className="relative z-10">
        <span className="banner-kicker"><span />THE DAILY BRIEF</span>
        <h2>A clear view.<br />A connected day.</h2>
        <p>
          Your appointments, care queues and next steps.<br className="hidden sm:block" />
          {" "}Everything you need to keep your clinic moving.
        </p>
        <Link href={calendarHref} className="banner-link">
          Open today’s calendar <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </div>
      <div className="banner-art" aria-hidden="true">
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="orbit orbit-three" />
        <div className="orbit-core"><Sparkles size={38} strokeWidth={1.2} /></div>
        <span className="orbit-node node-one"><CalendarDays size={20} /></span>
        <span className="orbit-node node-two"><Users size={19} /></span>
        <span className="orbit-node node-three"><Check size={18} /></span>
      </div>
      <div className="banner-date">
        <CalendarDays size={17} aria-hidden="true" />
        <div>
          <span>{data.today === null ? "Clinic date unavailable" : formatDay(data.today)}</span>
          <small>{data.timezone ?? "Calendar remains available"}</small>
        </div>
      </div>
    </div>
  );
}

type MetricProps = {
  label: string;
  value: number | null;
  description: string;
  href: string;
  icon: LucideIcon;
  tone: "teal" | "amber" | "violet" | "blue";
};

function Metric({ label, value, description, href, icon: Icon, tone }: MetricProps) {
  return (
    <Link href={href} className={`metric-card tone-${tone}`}
      aria-label={`${label}: ${value ?? "unavailable"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="metric-icon"><Icon size={19} strokeWidth={1.7} aria-hidden="true" /></span>
        <ArrowRight size={16} className="metric-arrow" aria-hidden="true" />
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <strong className="metric-value">{value === null ? "—" : value.toLocaleString("en-IN")}</strong>
        {value === null ? <span className="text-xs text-muted-foreground">Unavailable</span> : null}
      </div>
      <h2 className="mt-1 text-sm font-semibold">{label}</h2>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </Link>
  );
}

type PanelHeadingProps = { title: string; subtitle: string; href?: string; link?: string };

function PanelHeading({ title, subtitle, href, link }: PanelHeadingProps) {
  return (
    <div className="panel-heading">
      <div><h2>{title}</h2><p>{subtitle}</p></div>
      {href ? (
        <Link href={href} className="panel-link">{link}<ChevronRight size={15} aria-hidden="true" /></Link>
      ) : null}
    </div>
  );
}

function Agenda({ visits, href }: AgendaProps) {
  const sorted = visits?.toSorted((a, b) => a.starts_at.localeCompare(b.starts_at)) ?? [];
  return (
    <section className="dashboard-panel" aria-label="Today's appointments">
      <PanelHeading title="Today’s appointments" subtitle="A little preparation. A smoother day."
        href={href} link="View calendar" />
      {visits === null ? (
        <SectionMessage title="Schedule unavailable"
          text="We couldn’t load today’s appointments. Open the calendar to try again." />
      ) : visits.length === 0 ? (
        <SectionMessage title="Room for a fresh start" icon={CalendarDays}
          text="No appointments on today’s calendar. Find a patient to book their next visit." />
      ) : (
        <>
          <div className="agenda-labels" aria-hidden="true">
            <span>TIME</span><span>PATIENT / VISIT</span><span>STATUS</span>
          </div>
          <ul className="agenda-list">
            {sorted.slice(0, 6).map((visit) => <AgendaRow key={visit.id} visit={visit} />)}
          </ul>
          <div className="panel-foot">
            <span>Showing {Math.min(sorted.length, 6)} of {sorted.length} appointments</span>
            <Link href={href}>Manage schedule <ArrowRight size={14} aria-hidden="true" /></Link>
          </div>
        </>
      )}
    </section>
  );
}

const statusLabels: Record<string, string> = {
  scheduled: "Scheduled", arrived: "Arrived", in_progress: "In progress",
  completed: "Completed", cancelled: "Cancelled", no_show: "No-show",
};

function AgendaRow({ visit }: { visit: CalendarVisit }) {
  const initials = visit.patient.full_name.split(" ").filter(Boolean)
    .slice(0, 2).map((part) => part[0]).join("");
  return (
    <li className="agenda-row">
      <div className="agenda-time">
        <strong>{wallTime(visit.starts_at) ?? "—"}</strong>
        <small>{wallTime(visit.ends_at) ?? "—"}</small>
      </div>
      <div className="flex min-w-0 items-center gap-3">
        <span className="patient-avatar" aria-hidden="true">{initials}</span>
        <div className="min-w-0">
          <Link className="patient-name" href={`/patients/${encodeURIComponent(visit.patient.id)}`}>
            {visit.patient.full_name}
          </Link>
          <p className="truncate text-xs text-muted-foreground">
            {visit.appointment_type.name} <span aria-hidden="true">·</span> {visit.clinician.full_name}
          </p>
        </div>
      </div>
      <span className={`visit-status status-${visit.status}`}>
        <span />{statusLabels[visit.status] ?? visit.status}
      </span>
    </li>
  );
}

function DayProgress({ visits, href }: AgendaProps) {
  const completed = visits?.filter((visit) => visit.status === "completed").length ?? 0;
  const total = visits?.length ?? 0;
  const summary = visits === null ? "Unavailable" : total === 0
    ? "No appointments today" : `${completed} of ${total} visits completed`;
  return (
    <section className="day-progress">
      <div className="progress-symbol"><Layers3 size={22} aria-hidden="true" /></div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">One visit at a time</h2>
          <Link href={href} className="text-xs font-medium text-primary">
            {visits === null ? "Schedule unavailable" : `${completed} of ${total} visits completed`}
          </Link>
        </div>
        <div className="progress-track" role="progressbar" aria-label="Today's visits completed"
          aria-valuemin={0} aria-valuemax={total || 1} aria-valuenow={completed} aria-valuetext={summary}>
          <span style={{ width: `${total === 0 ? 0 : completed / total * 100}%` }} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {visits === null ? "Open the calendar to check your day." : total === 0
            ? "Your day’s progress will appear here." : "Small steps that keep care moving forward."}
        </p>
      </div>
    </section>
  );
}

function Attention({ data }: { data: DashboardData }) {
  const rows = data.followUps?.items.slice(0, 3) ?? [];
  return (
    <section className="dashboard-panel" aria-label="Attention queue">
      <PanelHeading title="Needs your attention" subtitle="Keep the next step within reach." />
      <div className="attention-summary">
        <span className="attention-mark"><PhoneCall size={17} aria-hidden="true" /></span>
        <div>
          <h3>Follow-ups due</h3>
          <p>{data.followUps === null ? "Queue unavailable" : data.followUps.total === 0
            ? "You’re all caught up" : `${data.followUps.total} waiting for a next step`}</p>
        </div>
        <Link href="/follow-ups" aria-label="Open follow-up queue"><ArrowRight size={17} /></Link>
      </div>
      {rows.length > 0 ? (
        <ul className="attention-list">
          {rows.map((row) => (
            <li key={row.id}>
              <div className="min-w-0">
                <Link href={`/patients/${encodeURIComponent(row.patient.id)}`} className="patient-name">
                  {row.patient.full_name}
                </Link>
                <p>{row.status === "contacted" ? "Contacted · ready to book" : "Awaiting contact"}</p>
              </div>
              <span className={`due-label ${row.timing === "overdue" ? "overdue" : ""}`}>
                {row.timing === "overdue" ? "Overdue" : "Due today"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <Link href="/follow-ups" className="attention-footer">
        Open follow-up queue <ArrowRight size={14} aria-hidden="true" />
      </Link>
      <div className="queue-links">
        <QueueLink href="/recalls" icon={RotateCcw} title="Recall queue"
          detail={data.recalls === null ? "Unavailable" : `${data.recalls.total} due`} />
        <QueueLink href="/lab" icon={FlaskConical} title="Lab coordination"
          detail={data.lab === null ? "Unavailable" : `${data.lab.total} open`} />
      </div>
    </section>
  );
}

type QueueLinkProps = { href: string; icon: LucideIcon; title: string; detail: string };

function QueueLink({ href, icon: Icon, title, detail }: QueueLinkProps) {
  return (
    <Link href={href} className="queue-link">
      <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
      <span>{title}</span><small>{detail}</small><ChevronRight size={14} aria-hidden="true" />
    </Link>
  );
}

function QuickActions() {
  return (
    <section className="dashboard-panel quick-actions">
      <PanelHeading title="A good next step" subtitle="The everyday essentials." />
      <QueueLink href="/patients/new" icon={Plus} title="Register a patient" detail="" />
      <QueueLink href="/patients" icon={Search} title="Find a patient & book" detail="" />
      <QueueLink href="/calendar" icon={CalendarDays} title="Plan the clinic day" detail="" />
      <div className="quick-note">
        <ArrowDownLeft size={16} aria-hidden="true" />
        <p>Care continues beyond the chair.<br /><strong>Keep every next visit connected.</strong></p>
      </div>
    </section>
  );
}

function OtherDashboard({ mode }: { mode: DashboardData["mode"] }) {
  return (
    <>
      <div className="inventory-welcome">
        <span className="metric-icon tone-teal"><Package size={26} aria-hidden="true" /></span>
        <p className="eyebrow mt-6">BEHIND EVERY SMOOTH CLINIC DAY</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Prepared for better care.</h2>
        <p className="mt-3 max-w-lg text-sm leading-7 text-muted-foreground">
          {mode === "inventory"
            ? "Keep the essentials organized. Manage clinic supplies, track batch stock and connect resources to each visit."
            : "Your clinic workspace is ready. Contact your clinic administrator if you need access to a workflow."}
        </p>
      </div>
      {mode === "inventory" ? (
        <div className="grid gap-5 sm:grid-cols-2">
          <Link href="/inventory" className="inventory-shortcut">
            <Package size={25} aria-hidden="true" />
            <h2>Clinic inventory</h2><p>Items, categories, batches and stock history.</p>
            <span>Open inventory <ArrowRight size={16} aria-hidden="true" /></span>
          </Link>
          <Link href="/inventory/rules" className="inventory-shortcut">
            <Layers3 size={25} aria-hidden="true" />
            <h2>Visit type rules</h2><p>The resources used when an appointment completes.</p>
            <span>View resource rules <ArrowRight size={16} aria-hidden="true" /></span>
          </Link>
        </div>
      ) : null}
    </>
  );
}

function SectionMessage({ title, text, icon: Icon = Clock3 }: {
  title: string; text: string; icon?: LucideIcon;
}) {
  return (
    <div className="section-message">
      <span><Icon size={24} strokeWidth={1.5} aria-hidden="true" /></span>
      <h3>{title}</h3><p>{text}</p>
    </div>
  );
}

function formatDay(date: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}
