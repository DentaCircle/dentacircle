import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { CareScreen } from "@/features/care/care-screen";
import type { CarePlan } from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const patientId = "00000000-0000-4000-8000-000000000010";

const plans: CarePlan[] = [
  {
    id: "plan-new",
    patient_id: patientId,
    title: "Newer plan",
    created_at: "2026-10-15T10:00:00+00:00",
    is_open: true,
    items: [
      { id: "item-planned", name: "Cleaning", status: "planned", created_at: "2026-10-15T10:01:00+00:00" },
      { id: "item-started", name: "Filling", status: "started", created_at: "2026-10-15T10:02:00+00:00" },
      { id: "item-done", name: "Crown", status: "completed", created_at: "2026-10-15T10:03:00+00:00" },
    ],
  },
  {
    id: "plan-old",
    patient_id: patientId,
    title: "Older plan",
    created_at: "2026-10-14T10:00:00+00:00",
    is_open: false,
    items: [
      { id: "item-cancelled", name: "Polish", status: "cancelled", created_at: "2026-10-14T10:01:00+00:00" },
    ],
  },
];

test("an empty page offers a new plan", () => {
  render(<CareScreen status="ready" patientId={patientId} plans={[]} canWrite notice={null} />);
  expect(screen.getByText("No care plans yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New care plan" })).toBeInTheDocument();
  expect(screen.getByLabelText("Title")).toBeInTheDocument();
});

test("plans show items, badges, and writer actions", () => {
  render(<CareScreen status="ready" patientId={patientId} plans={plans} canWrite notice="plan_added" />);
  expect(screen.getByRole("status")).toHaveTextContent("Care plan added.");
  const titles = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
  expect(titles).toEqual(["Newer plan", "Older plan"]);
  expect(screen.getByText("Open")).toBeInTheDocument();
  expect(screen.getByText("Finished")).toBeInTheDocument();
  expect(screen.getByText("Planned")).toBeInTheDocument();
  expect(screen.getByText("Started")).toBeInTheDocument();
  expect(screen.getByText("Completed")).toBeInTheDocument();
  expect(screen.getByText("Cancelled")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Start" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "Complete" })).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Cancel" })).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Rename" })).toHaveLength(2);
  expect(screen.getAllByText("Service name only. No clinical notes.")).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Add item" })).toHaveLength(2);
});

test("a receptionist sees the plans and no actions", () => {
  render(<CareScreen status="ready" patientId={patientId} plans={plans} canWrite={false} notice={null} />);
  expect(screen.getByText("Cleaning")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New care plan" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Complete" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
  expect(screen.queryByText("Service name only. No clinical notes.")).not.toBeInTheDocument();
});

test("load failures use the fixed sentences", () => {
  const { rerender } = render(
    <CareScreen status="error" patientId={patientId} plans={[]} canWrite={false} notice={null} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Care could not be loaded.");
  rerender(<CareScreen status="forbidden" patientId={patientId} plans={[]} canWrite={false} notice={null} />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  rerender(<CareScreen status="not-found" patientId={patientId} plans={[]} canWrite={false} notice={null} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");
});
