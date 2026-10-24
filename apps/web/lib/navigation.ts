export type NavItem = {
  href: "/" | "/patients" | "/calendar" | "/follow-ups" | "/recalls" | "/lab" | "/inventory" | "/status";
  label: string;
};

export const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/patients", label: "Patients" },
  { href: "/calendar", label: "Calendar" },
  { href: "/follow-ups", label: "Follow-ups" },
  { href: "/recalls", label: "Recalls" },
  { href: "/lab", label: "Lab" },
  { href: "/inventory", label: "Inventory" },
  { href: "/status", label: "Status" },
] as const satisfies readonly NavItem[];

export function isNavCurrent(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
