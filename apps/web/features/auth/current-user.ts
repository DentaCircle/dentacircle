import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getCurrentUser, type ApiResult, type CurrentUser } from "@/lib/api/client";

const SESSION_COOKIE = "dc_session";

export async function requireUser(): Promise<CurrentUser> {
  const result = await readSessionUser();
  if (result.ok) return result.data;
  if (result.error.kind === "api" && result.error.status === 401) redirect("/login");
  throw new Error("The page could not be shown.");
}

export async function redirectIfSignedIn(): Promise<void> {
  const result = await readSessionUser();
  if (result.ok) redirect("/");
}

async function readSessionUser(): Promise<ApiResult<CurrentUser>> {
  return getCurrentUser(await sessionCookieHeader());
}

async function sessionCookieHeader(): Promise<string> {
  const store = await cookies();
  const session = store.get(SESSION_COOKIE);
  if (session === undefined || session.value === "") return "";
  return `${SESSION_COOKIE}=${session.value}`;
}
