import Link from "next/link";

import { inventoryItemHref } from "@/features/inventory/links";
import type { HistoryView } from "@/features/inventory/rows";

export function HistoryPanel({ itemId, history }: { itemId: string; history: HistoryView }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-medium">History</h2>
      {history.status === "error" ? (
        <p role="alert">Stock history could not be loaded.</p>
      ) : null}
      {history.status === "empty" ? <p>No stock movements yet.</p> : null}
      {history.status === "ready" ? (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium" scope="col">
                  Type
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Reason
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Change
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Batch
                </th>
                <th className="py-2 pr-3 font-medium" scope="col">
                  Who
                </th>
                <th className="py-2 font-medium" scope="col">
                  When
                </th>
              </tr>
            </thead>
            <tbody>
              {history.rows.map((row) => (
                <tr key={row.id} className="border-b">
                  <td className="py-2 pr-3">
                    {row.visitHref === null ? (
                      row.typeLabel
                    ) : (
                      <Link href={row.visitHref}>{row.typeLabel}</Link>
                    )}
                  </td>
                  <td className="py-2 pr-3">{row.reasonLabel}</td>
                  <td className="py-2 pr-3">{row.changeLabel}</td>
                  <td className="py-2 pr-3">{row.batchNumber}</td>
                  <td className="py-2 pr-3">{row.recordedBy}</td>
                  <td className="py-2">{row.whenLabel}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav aria-label="Stock history pages" className="flex gap-3">
            {history.page > 1 ? (
              <Link href={inventoryItemHref(itemId, undefined, history.page - 1)}>Previous</Link>
            ) : (
              <span>Previous</span>
            )}
            {history.page * history.pageSize < history.total ? (
              <Link href={inventoryItemHref(itemId, undefined, history.page + 1)}>Next</Link>
            ) : (
              <span>Next</span>
            )}
          </nav>
        </>
      ) : null}
    </section>
  );
}
