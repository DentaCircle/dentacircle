import type { ReactNode } from "react";

import { MainNav } from "@/components/main-nav";
import { MobileNav } from "@/components/mobile-nav";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <MobileNav />
        <p className="text-lg font-semibold">Dentacircle</p>
      </header>
      <div className="flex">
        <aside className="hidden w-56 shrink-0 border-r p-4 md:block">
          <MainNav />
        </aside>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
