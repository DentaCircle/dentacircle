import { requireUser } from "@/features/auth/current-user";
import { canRegisterPatients } from "@/features/patients/access";
import { NewPatientScreen } from "@/features/patients/new-patient-screen";

export const dynamic = "force-dynamic";

export default async function NewPatientPage() {
  const user = await requireUser();
  return <NewPatientScreen canCreate={canRegisterPatients(user.roles)} />;
}
