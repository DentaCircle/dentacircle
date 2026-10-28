import { requireUser } from "@/features/auth/current-user";
import { DashboardScreen } from "@/features/dashboard/dashboard-screen";
import { loadDashboard } from "@/features/dashboard/load-dashboard";
import { sessionCookieHeader } from "@/features/patients/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const user = await requireUser();
  const data = await loadDashboard(user, await sessionCookieHeader());
  return <DashboardScreen user={user} data={data} />;
}
