import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PatientForm, type PatientFormValues } from "@/features/patients/patient-form";

type EditPatientScreenProps = {
  canEdit: boolean;
  patientId?: string;
  initial?: PatientFormValues;
};

export function EditPatientScreen({ canEdit, patientId, initial }: EditPatientScreenProps) {
  if (!canEdit || patientId === undefined || initial === undefined) {
    return (
      <section>
        <h1 className="mb-4 text-2xl font-semibold">Edit patient</h1>
        <p role="alert">You do not have access.</p>
      </section>
    );
  }

  return (
    <section className="flex max-w-md flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Edit patient</h1>
        <Link href={`/patients/${patientId}`}>Patient</Link>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <PatientForm mode="edit" patientId={patientId} initial={initial} />
        </CardContent>
      </Card>
    </section>
  );
}
