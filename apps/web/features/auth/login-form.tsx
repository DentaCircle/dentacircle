"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const WRONG_CREDENTIALS_MESSAGE = "Email or password is wrong.";
const MISSING_CREDENTIALS_MESSAGE = "Enter an email and password.";
const UNREACHABLE_MESSAGE = "Could not reach the server.";

export function LoginForm() {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setMessage(null);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      if (response.ok) {
        router.push("/");
        router.refresh();
        return;
      }
      setPassword("");
      setMessage(failureMessage(response.status));
    } catch {
      setPassword("");
      setMessage(UNREACHABLE_MESSAGE);
    }

    isSubmittingRef.current = false;
    setIsSubmitting(false);
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit}>
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      {message === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        Sign in
      </Button>
    </form>
  );
}

function failureMessage(status: number): string {
  if (status === 401) return WRONG_CREDENTIALS_MESSAGE;
  if (status === 422) return MISSING_CREDENTIALS_MESSAGE;
  return UNREACHABLE_MESSAGE;
}
