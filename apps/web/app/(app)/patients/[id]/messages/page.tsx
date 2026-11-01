import { Conversation } from "@/features/messages/conversation";
import { sessionCookieHeader } from "@/features/patients/session";
import { getClinicDay } from "@/lib/api/client";

export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const day = await getClinicDay(await sessionCookieHeader());
  if (!day.ok) return <p role="alert">Clinic details could not be loaded.</p>;
  return <Conversation patientId={id} timezone={day.data.timezone} />;
}
