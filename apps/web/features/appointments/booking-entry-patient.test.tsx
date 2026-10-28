import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { BookPage } from "@/features/appointments/book-page";
import { FollowUpBookPage } from "@/features/follow-ups/book-page";
import { RecallBookPage } from "@/features/recalls/book-page";

vi.mock("@/features/appointments/book-screen", () => ({
  BookScreen: ({ patient }: { patient: { full_name: string; display_id: string } }) =>
    <p>{patient.full_name} · {patient.display_id}</p>,
}));

const patient = { full_name: "Sample Patient", display_id: "P-0001" };
const shared = { patient, types: [], clinicians: [], today: "2026-10-12" };

test("every booking entry passes patient identity to the form", () => {
  const { rerender } = render(<BookPage status="ready" patientId="p-1" {...shared} />);
  expect(screen.getByText("Sample Patient · P-0001")).toBeInTheDocument();
  rerender(<FollowUpBookPage status="ready" followUpId="f-1" {...shared} />);
  expect(screen.getByText("Sample Patient · P-0001")).toBeInTheDocument();
  rerender(<RecallBookPage status="ready" recallId="r-1" {...shared} />);
  expect(screen.getByText("Sample Patient · P-0001")).toBeInTheDocument();
});
