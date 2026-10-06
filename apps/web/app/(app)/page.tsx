import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/features/auth/current-user";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const user = await requireUser();

  return (
    <section>
      <h1 className="mb-4 text-2xl font-semibold">Dashboard</h1>
      <Card>
        <CardHeader>
          <CardTitle>{user.full_name}</CardTitle>
          <CardDescription>{user.clinic.name}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul aria-label="Roles" className="flex flex-wrap gap-2">
            {user.roles.map((role) => (
              <li key={role}>
                <Badge>{role}</Badge>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
