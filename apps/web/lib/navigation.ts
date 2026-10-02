export type NavItem = {
  href: "/" | "/status";
  label: string;
};

export const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/status", label: "Status" },
] as const satisfies readonly NavItem[];
