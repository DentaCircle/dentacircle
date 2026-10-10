export type NavItem = {
  href: "/" | "/patients" | "/status";
  label: string;
};

export const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/patients", label: "Patients" },
  { href: "/status", label: "Status" },
] as const satisfies readonly NavItem[];

export function isNavCurrent(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
