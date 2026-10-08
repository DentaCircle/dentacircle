import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NewPatientForm } from "@/features/patients/new-patient-form";

export function NewPatientScreen({ canCreate }: { canCreate: boolean }) {
  if (!canCreate) {
    return (
      <section>
        <h1 className="mb-4 text-2xl font-semibold">New patient</h1>
        <p role="alert">You do not have access.</p>
      </section>
    );
  }

  return (
    <section className="flex max-w-md flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">New patient</h1>
        <Link href="/patients">Patients</Link>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Register</CardTitle>
        </CardHeader>
        <CardContent>
          <NewPatientForm />
        </CardContent>
      </Card>
    </section>
  );
}
