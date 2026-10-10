import { cookies } from "next/headers";

const SESSION_COOKIE = "dc_session";

export async function sessionCookieHeader(): Promise<string> {
  const store = await cookies();
  const session = store.get(SESSION_COOKIE);
  if (session === undefined || session.value === "") return "";
  return `${SESSION_COOKIE}=${session.value}`;
}
