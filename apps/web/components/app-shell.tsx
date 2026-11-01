import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

import { MainNav } from "@/components/main-nav";
import { MobileNav } from "@/components/mobile-nav";
import { SignOutButton } from "@/features/auth/sign-out-button";
import type { CurrentUser } from "@/lib/api/client";

export function AppShell({ user, children }: { user: CurrentUser; children: ReactNode }) {
  const initials = user.full_name.split(" ").filter(Boolean)
    .slice(0, 2).map((name) => name[0]).join("");
  return (
    <div className="app-frame min-h-screen bg-background text-foreground">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="app-header">
        <div className="flex shrink-0 items-center gap-3">
          <MobileNav />
          <div className="brand-mark" aria-hidden="true"><Sparkles size={22} strokeWidth={1.6} /></div>
          <p className="brand-name">
            denta<span>circle</span><span className="sr-only">Dentacircle</span>
          </p>
        </div>
        <div className="header-clinic hidden lg:flex">
          <span className="clinic-dot shrink-0" />
          <span className="truncate">{user.clinic.name}</span>
          <span className="workspace-label shrink-0">Clinic workspace</span>
        </div>
        <div className="ml-auto flex min-w-0 items-center gap-3 sm:gap-4">
          <div className="hidden min-w-0 text-right sm:block">
            <p className="truncate text-sm font-semibold">{user.full_name}</p>
            <p className="max-w-48 truncate text-xs text-muted-foreground lg:hidden">{user.clinic.name}</p>
            <p className="hidden text-xs text-muted-foreground lg:block">Care team</p>
          </div>
          <span className="user-avatar" role="img" aria-label={`${user.full_name} · ${user.clinic.name}`}>
            {initials}
          </span>
          <SignOutButton />
        </div>
      </header>
      <div className="app-body flex">
        <aside className="app-sidebar hidden shrink-0 md:block">
          <div className="sidebar-inner">
            <MainNav />

          </div>
        </aside>
        <main id="main-content" className="workspace-main min-w-0 flex-1" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
