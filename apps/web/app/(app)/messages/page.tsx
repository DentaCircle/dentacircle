import { Inbox } from "@/features/messages/inbox";
import { sessionCookieHeader } from "@/features/patients/session";
import { getClinicDay } from "@/lib/api/client";

export default async function MessagesPage() {
  const day = await getClinicDay(await sessionCookieHeader());
  if (!day.ok) return <p role="alert">Clinic details could not be loaded.</p>;
  return <Inbox timezone={day.data.timezone} />;
}
