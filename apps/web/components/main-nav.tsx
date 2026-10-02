"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navItems } from "@/lib/navigation";

type MainNavProps = {
  onNavigate?: () => void;
};

export function MainNav({ onNavigate }: MainNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label="Main">
      <ul className="flex flex-col gap-1">
        {navItems.map((item) => {
          const isCurrent = pathname === item.href;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={isCurrent ? "page" : undefined}
                className="block rounded-md px-3 py-2 text-sm hover:bg-muted aria-[current=page]:bg-muted aria-[current=page]:font-medium"
                onClick={onNavigate}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
