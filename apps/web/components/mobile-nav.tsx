"use client";

import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { MainNav } from "@/components/main-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="icon" className="md:hidden" aria-label="Open menu">
          <MenuIcon />
        </Button>
      </SheetTrigger>
      <SheetContent side="left">
        <SheetHeader>
          <SheetTitle>Dentacircle</SheetTitle>
          <SheetDescription className="sr-only">Navigate your clinic workspace.</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
          <MainNav onNavigate={() => setIsOpen(false)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
