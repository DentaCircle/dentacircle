import type { ReactNode } from "react";

import { MainNav } from "@/components/main-nav";
import { MobileNav } from "@/components/mobile-nav";
import { SignOutButton } from "@/features/auth/sign-out-button";
import type { CurrentUser } from "@/lib/api/client";

type AppShellProps = {
  user: CurrentUser;
  children: ReactNode;
};

export function AppShell({ user, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
        <MobileNav />
        <p className="text-lg font-semibold">Dentacircle</p>
        <div className="ml-auto flex min-w-0 items-center gap-3">
          <p className="truncate text-sm">
            <span className="font-medium">{user.full_name}</span>
            <span className="text-muted-foreground"> · {user.clinic.name}</span>
          </p>
          <SignOutButton />
        </div>
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
