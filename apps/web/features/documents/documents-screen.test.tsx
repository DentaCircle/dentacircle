import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import {
  DocumentsScreen,
  type DocumentsScreenProps,
} from "@/features/documents/documents-screen";
import type { DocumentRowData } from "@/features/documents/rows";
import { listDocumentsInBrowser, type DocumentItem, type DocumentPage } from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/client", () => ({
  listDocumentsInBrowser: vi.fn(),
  updateDocumentLinks: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listDocumentsInBrowser).mockReset();
});

const patientId = "00000000-0000-4000-8000-000000000010";

const row: DocumentRowData = {
  id: "doc-1",
  filename: "report.pdf",
  type: "PDF",
  size: "2.0 KB",
  uploadedBy: "Sample Desk",
  uploadedAt: "2026-10-12 10:05",
  href: `/api/patients/${patientId}/documents/doc-1/file`,
  viewerHref: `/patients/${patientId}/documents/doc-1`,
  links: [],
  contentType: "application/pdf",
};

function props(overrides: Partial<DocumentsScreenProps>): DocumentsScreenProps {
  return {
    status: "ready",
    patientId,
    rows: [row],
    page: 1,
    pageSize: 20,
    total: 1,
    canUpload: true,
    isPatientInactive: false,
    notice: null,
    ...overrides,
  };
}

test("shows each row with its name, type, size, who, when and a download link", () => {
  render(<DocumentsScreen {...props({})} />);

  expect(screen.getByRole("heading", { name: "Documents" })).toBeInTheDocument();
  expect(screen.getByText("report.pdf")).toBeInTheDocument();
  expect(screen.getByText("PDF")).toBeInTheDocument();
  expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  expect(screen.getByText("Sample Desk, 2026-10-12 10:05")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", row.href);
  expect(screen.getByLabelText("File")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
});

test("the file name is shown as text, never as markup", () => {
  render(
    <DocumentsScreen
      {...props({ rows: [{ ...row, filename: "<img src=x onerror=alert(1)>.pdf" }] })}
    />,
  );
  expect(screen.getByText("<img src=x onerror=alert(1)>.pdf")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
});

test("the empty state keeps the upload form", () => {
  render(<DocumentsScreen {...props({ status: "empty", rows: [], total: 0 })} />);
  expect(screen.getByText("No documents for this patient yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
});

test("an inactive patient has no upload form and the page says why", () => {
  render(<DocumentsScreen {...props({ isPatientInactive: true })} />);
  expect(
    screen.getByText("This patient is inactive, so new documents cannot be added."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("File")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download" })).toBeInTheDocument();
});

test("an inactive patient with no documents still says why", () => {
  render(
    <DocumentsScreen {...props({ status: "empty", rows: [], total: 0, isPatientInactive: true })} />,
  );
  expect(screen.getByText("No documents for this patient yet.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
});

test("the no-access, not-found and error states show no list and no form", () => {
  const blank = { rows: [], total: 0, canUpload: false };
  const { rerender } = render(<DocumentsScreen {...props({ ...blank, status: "forbidden" })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<DocumentsScreen {...props({ ...blank, status: "not-found" })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");

  rerender(<DocumentsScreen {...props({ ...blank, status: "error" })} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Documents could not be loaded.");

  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
});

test("a role that cannot upload sees the list without the form", () => {
  render(<DocumentsScreen {...props({ canUpload: false })} />);
  expect(screen.getByText("report.pdf")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
});

test("shows the upload notice", () => {
  render(<DocumentsScreen {...props({ notice: "uploaded" })} />);
  expect(screen.getByRole("status")).toHaveTextContent("Document uploaded.");
});

test("pages link to the next and previous page", () => {
  render(<DocumentsScreen {...props({ page: 2, total: 41 })} />);
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
    "href",
    `/patients/${patientId}/documents?page=1`,
  );
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
    "href",
    `/patients/${patientId}/documents?page=3`,
  );
});

test("a visit filter shows its heading, an unlink, and the other documents", async () => {
  const user = userEvent.setup();
  vi.mocked(listDocumentsInBrowser).mockResolvedValue({
    ok: true,
    data: pageOf([listed("doc-2", "other.pdf", null), listed("doc-3", "already.pdf", "visit-1")], 2),
  });
  render(
    <DocumentsScreen
      {...props({
        context: { kind: "visit", id: "visit-1" },
        contextHeading: "Documents for Consultation, 2026-10-12 10:00",
        rows: [{ ...row, links: ["Visit: Consultation, 2026-10-12 10:00"] }],
        notice: "linked",
      })}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Documents for Consultation, 2026-10-12 10:00" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Show all documents" })).toHaveAttribute(
    "href",
    `/patients/${patientId}/documents?page=1`,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Document linked.");
  expect(screen.getByRole("button", { name: "Unlink" })).toBeInTheDocument();
  expect(screen.getByText("Visit: Consultation, 2026-10-12 10:00")).toBeInTheDocument();
  expect(listDocumentsInBrowser).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Link a document that is already uploaded" }));
  expect(await screen.findByText("other.pdf")).toBeInTheDocument();
  expect(screen.queryByText("already.pdf")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Link" })).toBeInTheDocument();
  expect(listDocumentsInBrowser).toHaveBeenCalledWith(patientId, 1, 100);
});

test("load more fetches the next page and keeps the earlier files", async () => {
  const user = userEvent.setup();
  vi.mocked(listDocumentsInBrowser)
    .mockResolvedValueOnce({
      ok: true,
      data: pageOf([listed("doc-2", "other.pdf", null)], 101, 1),
    })
    .mockResolvedValueOnce({
      ok: true,
      data: pageOf([listed("doc-101", "later.pdf", null)], 101, 2),
    });
  render(
    <DocumentsScreen
      {...props({
        context: { kind: "visit", id: "visit-1" },
        contextHeading: "Documents for this visit",
      })}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Link a document that is already uploaded" }));
  expect(await screen.findByText("other.pdf")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("later.pdf")).toBeInTheDocument();
  expect(screen.getByText("other.pdf")).toBeInTheDocument();
  expect(listDocumentsInBrowser).toHaveBeenLastCalledWith(patientId, 2, 100);
});

function listed(id: string, filename: string, appointmentId: string | null): DocumentItem {
  return {
    id,
    filename,
    content_type: "application/pdf",
    size_bytes: 20,
    uploaded_at: "2026-10-12T10:05:00+05:30",
    uploaded_by: { id: "user-1", name: "Sample Desk" },
    appointment:
      appointmentId === null
        ? null
        : {
            id: appointmentId,
            starts_at: "2026-10-12T10:00:00+05:30",
            type_name: "Consultation",
          },
    follow_up: null,
  };
}

function pageOf(items: DocumentItem[], total: number, page = 1): DocumentPage {
  return { items, total, page, page_size: 100 };
}

test("the first and last pages have no link in that direction", () => {
  render(<DocumentsScreen {...props({ page: 1, total: 1 })} />);
  expect(screen.queryByRole("link", { name: "Previous" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Next" })).not.toBeInTheDocument();
});
