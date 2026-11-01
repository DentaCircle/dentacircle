import { canCreateFollowUp, canReadCare, canWriteCare } from "@/features/care/access";
import { CareScreen, type CareScreenProps, type FollowUpLoad } from "@/features/care/care-screen";
import { isCareNotice } from "@/features/care/notices";
import { PatientWorkspace } from "@/features/patients/patient-workspace";
import { requireUser } from "@/features/auth/current-user";
import { sessionCookieHeader } from "@/features/patients/session";
import { getFollowUp, getPatient, listCarePlans } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type CarePageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ notice?: string }>;
};

export default async function CarePage({ params, searchParams }: CarePageProps) {
  const { id } = await params;
  const query = await searchParams;
  const notice = isCareNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canReadCare(user.roles)) {
    return (
      <CareScreen
        status="forbidden"
        patientId={id}
        plans={[]}
        canWrite={false}
        canCreateFollowUp={false}
        notice={null}
        followUp={{ status: "hidden" }}
      />
    );
  }
  const cookieHeader = await sessionCookieHeader();
  const result = await listCarePlans(cookieHeader, id);
  if (!result.ok) {
    return (
      <CareScreen
        {...failureProps(result.error)}
        patientId={id}
        canCreateFollowUp={false}
        notice={null}
        followUp={{ status: "hidden" }}
      />
    );
  }
  const [followUp, patient] = await Promise.all([getFollowUp(cookieHeader, id), getPatient(cookieHeader, id)]);
  return (
    <PatientWorkspace patient={patient.ok ? patient.data : null} current="care">
    <CareScreen
      status="ready"
      patientId={id}
      plans={result.data}
      canWrite={canWriteCare(user.roles)}
      canCreateFollowUp={canCreateFollowUp(user.roles)}
      notice={notice}
      followUp={followUpLoad(followUp)}
    />
    </PatientWorkspace>
  );
}

function followUpLoad(
  result: Awaited<ReturnType<typeof getFollowUp>>,
): FollowUpLoad {
  if (!result.ok) return { status: "error" };
  return { status: "ready", followUp: result.data.follow_up };
}

function failureProps(error: {
  kind: string;
  status?: number;
}): Pick<CareScreenProps, "status" | "plans" | "canWrite"> {
  const forbidden = error.kind === "api" && error.status === 403;
  const missing = error.kind === "api" && error.status === 404;
  if (forbidden) return { status: "forbidden", plans: [], canWrite: false };
  if (missing) return { status: "not-found", plans: [], canWrite: false };
  return { status: "error", plans: [], canWrite: false };
}
