"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export function SignOutButton() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSignOut() {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) return;
      router.push("/login");
      router.refresh();
    } catch {
      return;
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Button type="button" variant="outline" disabled={isSubmitting} onClick={onSignOut}>
      Sign out
    </Button>
  );
}
