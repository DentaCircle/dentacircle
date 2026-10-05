"use client";

import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { MainNav } from "@/components/main-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
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
        </SheetHeader>
        <MainNav onNavigate={() => setIsOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}
