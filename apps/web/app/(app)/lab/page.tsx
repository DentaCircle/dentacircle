import { requireUser } from "@/features/auth/current-user";
import { canUseLab } from "@/features/lab/access";
import { ClinicLabScreen, type ClinicLabScreenProps } from "@/features/lab/clinic-screen";
import { pageFromQuery, viewFromQuery } from "@/features/lab/links";
import { isLabNotice } from "@/features/lab/notices";
import { labRow } from "@/features/lab/rows";
import { sessionCookieHeader } from "@/features/patients/session";
import { listClinicLabWork } from "@/lib/api/client";

export const dynamic = "force-dynamic";

type ClinicLabPageProps = {
  searchParams: Promise<{ view?: string; page?: string; notice?: string }>;
};

export default async function ClinicLabPage({ searchParams }: ClinicLabPageProps) {
  const query = await searchParams;
  const view = viewFromQuery(query.view);
  const page = pageFromQuery(query.page);
  const notice = isLabNotice(query.notice) ? query.notice : null;
  const user = await requireUser();
  if (!canUseLab(user.roles)) {
    return <ClinicLabScreen {...blankProps("forbidden", view, page, notice)} />;
  }
  const found = await listClinicLabWork(await sessionCookieHeader(), view, page);
  if (!found.ok) {
    const forbidden = found.error.kind === "api" && found.error.status === 403;
    return <ClinicLabScreen {...blankProps(forbidden ? "forbidden" : "error", view, page, notice)} />;
  }
  if (found.data.total === 0) {
    return <ClinicLabScreen {...blankProps("empty", view, page, notice)} />;
  }
  return (
    <ClinicLabScreen
      status="ready"
      rows={found.data.items.map((item) => labRow(item))}
      total={found.data.total}
      page={found.data.page}
      pageSize={found.data.page_size}
      view={view}
      notice={notice}
    />
  );
}

function blankProps(
  status: "empty" | "forbidden" | "error",
  view: ClinicLabScreenProps["view"],
  page: number,
  notice: ClinicLabScreenProps["notice"],
): ClinicLabScreenProps {
  return {
    status,
    rows: [],
    total: 0,
    page,
    pageSize: 20,
    view,
    notice,
  };
}
