import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { patientsHref, type PatientStatusFilter } from "@/features/patients/links";
import { PatientSearchForm } from "@/features/patients/patient-search-form";

export type PatientRow = {
  id: string;
  displayId: string;
  fullName: string;
  phone: string;
  dateOfBirth: string | null;
  status: "active" | "inactive";
};

export type PatientListProps = {
  status: "ready" | "empty" | "no-match" | "forbidden" | "error";
  items: PatientRow[];
  total: number;
  page: number;
  pageSize: number;
  query: string;
  statusFilter: PatientStatusFilter;
  canCreate: boolean;
  createdDisplayId: string | null;
};

export function PatientList({
  status,
  items,
  total,
  page,
  pageSize,
  query,
  statusFilter,
  canCreate,
  createdDisplayId,
}: PatientListProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Patients</h1>
        {canCreate && status !== "forbidden" ? (
          <Button asChild>
            <Link href="/patients/new">New patient</Link>
          </Button>
        ) : null}
      </div>
      {createdDisplayId === null ? null : (
        <p role="status">Saved {createdDisplayId}.</p>
      )}
      {status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {status === "error" ? <p role="alert">Patients could not be loaded.</p> : null}
      {status === "forbidden" ? null : (
        <>
          <StatusLinks query={query} statusFilter={statusFilter} />
          <PatientSearchForm query={query} statusFilter={statusFilter} />
        </>
      )}
      {status === "empty" ? <p>No patients yet</p> : null}
      {status === "no-match" ? <p>No patients match</p> : null}
      {status === "ready" ? (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium" scope="col">
                  ID
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Name
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Phone
                </th>
                <th className="py-2 font-medium" scope="col">
                  Date of birth
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((patient) => (
                <tr key={patient.displayId} className="border-b">
                  <td className="py-2 pr-3">
                    <Link href={`/patients/${patient.id}`}>
                      <Badge>{patient.displayId}</Badge>
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <Link href={`/patients/${patient.id}`} className="font-medium underline">
                      {patient.fullName}
                    </Link>
                    {patient.status === "inactive" ? (
                      <Badge variant="secondary" className="ml-2">
                        Inactive
                      </Badge>
                    ) : null}
                  </td>
                  <td className="py-2 pr-3">{patient.phone}</td>
                  <td className="py-2">{patient.dateOfBirth ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 ? <p>No patients on this page.</p> : null}
          <nav aria-label="Pages" className="flex gap-3">
            {page > 1 ? (
              <Link href={patientsHref(query, page - 1, statusFilter)}>Previous</Link>
            ) : (
              <span>Previous</span>
            )}
            {page * pageSize < total ? (
              <Link href={patientsHref(query, page + 1, statusFilter)}>Next</Link>
            ) : (
              <span>Next</span>
            )}
          </nav>
        </>
      ) : null}
    </section>
  );
}

function StatusLinks({ query, statusFilter }: { query: string; statusFilter: PatientStatusFilter }) {
  const filters = [
    ["all", "All"],
    ["active", "Active"],
    ["inactive", "Inactive"],
  ] as const;
  return (
    <nav aria-label="Status" className="flex gap-3 text-sm">
      {filters.map(([value, label]) => (
        <Link
          key={value}
          href={patientsHref(query, 1, value)}
          aria-current={statusFilter === value ? "page" : undefined}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
