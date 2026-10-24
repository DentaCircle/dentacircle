import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { ViewerScreen, type ViewerScreenProps } from "@/features/documents/viewer-screen";
import type { DocumentRowData } from "@/features/documents/rows";

const patientId = "00000000-0000-4000-8000-000000000010";

function row(contentType: DocumentRowData["contentType"]): DocumentRowData {
  return {
    id: "doc-1",
    filename: contentType === "application/pdf" ? "report.pdf" : "scan.png",
    type: contentType === "application/pdf" ? "PDF" : "PNG",
    size: "2.0 KB",
    uploadedBy: "Sample Desk",
    uploadedAt: "2026-10-12 10:05",
    href: `/api/patients/${patientId}/documents/doc-1/file`,
    viewerHref: `/patients/${patientId}/documents/doc-1`,
    links: ["Visit: Consultation, 2026-10-12 10:00"],
    contentType,
  };
}

function props(overrides: Partial<ViewerScreenProps>): ViewerScreenProps {
  return { status: "ready", patientId, row: row("image/png"), ...overrides };
}

test("a PNG is shown as an image and a PDF opens in a new tab", () => {
  const { rerender } = render(<ViewerScreen {...props({})} />);
  const image = screen.getByRole("img", { name: "scan.png" });
  expect(image).toHaveAttribute(
    "src",
    `/api/patients/${patientId}/documents/doc-1/file?disposition=inline`,
  );
  expect(screen.queryByRole("link", { name: "Open in new tab" })).not.toBeInTheDocument();
  expect(screen.getByText("Visit: Consultation, 2026-10-12 10:00")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", row("image/png").href);

  rerender(<ViewerScreen {...props({ row: row("application/pdf") })} />);
  const opened = screen.getByRole("link", { name: "Open in new tab" });
  expect(opened).toHaveAttribute(
    "href",
    `/api/patients/${patientId}/documents/doc-1/file?disposition=inline`,
  );
  expect(opened).toHaveAttribute("target", "_blank");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("not-found, no-access and error match the documents page", () => {
  const { rerender } = render(<ViewerScreen {...props({ status: "not-found", row: null })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");
  rerender(<ViewerScreen {...props({ status: "forbidden", row: null })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  rerender(<ViewerScreen {...props({ status: "error", row: null })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Documents could not be loaded.");
  expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
});
