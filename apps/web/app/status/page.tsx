import { StatusCard } from "@/features/status/status-card";
import { getHealth, getReadiness } from "@/lib/api/client";

export const dynamic = "force-dynamic";

export default async function StatusPage() {
  const [health, ready] = await Promise.all([getHealth(), getReadiness()]);

  return (
    <section>
      <h1 className="mb-4 text-2xl font-semibold">Status</h1>
      <StatusCard health={health} ready={ready} />
    </section>
  );
}
