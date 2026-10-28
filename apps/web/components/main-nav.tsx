"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, CalendarDays, FlaskConical, LayoutDashboard, Package,
  PhoneCall, RotateCcw, Users, type LucideIcon,
} from "lucide-react";

import { isNavCurrent, navItems, type NavItem } from "@/lib/navigation";

const icons: Record<NavItem["href"], LucideIcon> = {
  "/": LayoutDashboard, "/patients": Users, "/calendar": CalendarDays,
  "/follow-ups": PhoneCall, "/recalls": RotateCcw, "/lab": FlaskConical,
  "/inventory": Package, "/status": Activity,
};

type MainNavProps = { onNavigate?: () => void };

export function MainNav({ onNavigate }: MainNavProps) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="main-nav">
      <p className="nav-caption">WORKSPACE</p>
      <ul className="flex flex-col gap-1.5">
        {navItems.map((item) => {
          const Icon = icons[item.href];
          return (
            <li key={item.href} className={item.href === "/status" ? "mt-6 border-t pt-5" : undefined}>
              <Link href={item.href} aria-current={isNavCurrent(pathname, item.href) ? "page" : undefined}
                className="nav-link" onClick={onNavigate}>
                <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
                {item.label}
                {isNavCurrent(pathname, item.href) ? <span className="nav-dot" aria-hidden="true" /> : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
