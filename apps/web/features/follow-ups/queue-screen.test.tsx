import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { QueueScreen, type QueueRow } from "@/features/follow-ups/queue-screen";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const overdue: QueueRow = {
  id: "fu-1",
  status: "scheduled",
  dueOn: "2026-10-19",
  timing: "overdue",
  patient: {
    id: "p-1",
    displayId: "P-0001",
    fullName: "Sample Ada",
    phone: "9000000001",
  },
};

const dueToday: QueueRow = {
  id: "fu-2",
  status: "contacted",
  dueOn: "2026-10-20",
  timing: "due_today",
  patient: {
    id: "p-2",
    displayId: "P-0002",
    fullName: "Sample Bea",
    phone: "9000000002",
  },
};

const upcoming: QueueRow = {
  id: "fu-3",
  status: "booked",
  dueOn: "2026-10-27",
  timing: "upcoming",
  patient: {
    id: "p-3",
    displayId: "P-0003",
    fullName: "Sample Cyd",
    phone: "9000000003",
  },
};

test("shows name, id, phone, due date, badges, status and actions", () => {
  render(
    <QueueScreen
      status="ready"
      items={[overdue, dueToday, upcoming]}
      total={3}
      page={1}
      pageSize={20}
      view="all"
      notice={null}
    />,
  );

  expect(screen.getByRole("link", { name: "Sample Ada" })).toHaveAttribute("href", "/patients/p-1");
  expect(screen.getByText("P-0001")).toBeInTheDocument();
  expect(screen.getByText("9000000001")).toBeInTheDocument();
  expect(screen.getByText("19 Oct 2026")).toBeInTheDocument();
  expect(screen.getByText("Overdue")).toBeInTheDocument();
  expect(screen.getByText("Due today")).toBeInTheDocument();
  expect(screen.getByText("Upcoming")).toBeInTheDocument();
  expect(screen.getByText("Scheduled")).toBeInTheDocument();
  expect(screen.getByText("Contacted")).toBeInTheDocument();
  expect(screen.getByText("Booked")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark contacted" })).toBeInTheDocument();
  const bookLinks = screen.getAllByRole("link", { name: "Book visit" });
  expect(bookLinks).toHaveLength(2);
  expect(bookLinks[0]).toHaveAttribute("href", "/follow-ups/fu-1/book");
  expect(bookLinks[1]).toHaveAttribute("href", "/follow-ups/fu-2/book");
  expect(screen.getAllByRole("button", { name: "Cancel follow-up" })).toHaveLength(3);
  expect(screen.getByRole("link", { name: "All open" })).toHaveAttribute("aria-current", "page");
});

test("due view switch and empty copy", () => {
  const { rerender } = render(
    <QueueScreen
      status="empty"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      view="due"
      notice={null}
    />,
  );
  expect(screen.getByText("No follow-ups are due.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Due" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "All open" })).toHaveAttribute("href", "/follow-ups?view=all&page=1");

  rerender(
    <QueueScreen
      status="forbidden"
      items={[]}
      total={0}
      page={1}
      pageSize={20}
      view="due"
      notice={null}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByRole("link", { name: "Due" })).not.toBeInTheDocument();
});

test("pagination and notices", () => {
  render(
    <QueueScreen
      status="ready"
      items={[overdue]}
      total={45}
      page={2}
      pageSize={20}
      view="due"
      notice="booked"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Visit booked.");
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/follow-ups?page=1");
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "/follow-ups?page=3");
});

test("a booked row can be cancelled and has no book or contacted action", () => {
  render(
    <QueueScreen
      status="ready"
      items={[upcoming]}
      total={1}
      page={1}
      pageSize={20}
      view="all"
      notice="cancelled"
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Follow-up cancelled.");
  expect(screen.getByRole("button", { name: "Cancel follow-up" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Mark contacted" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Book visit" })).not.toBeInTheDocument();
});

test("empty views guide staff to all open follow-ups and patient care", () => {
  const { rerender } = render(<QueueScreen status="empty" items={[]} total={0} page={1}
    pageSize={20} view="due" notice={null} />);
  expect(screen.getByText(/Choose All open/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Find a patient" })).toHaveAttribute("href", "/patients");
  rerender(<QueueScreen status="empty" items={[]} total={0} page={1}
    pageSize={20} view="all" notice={null} />);
  expect(screen.getByText("There are no open follow-ups.")).toBeInTheDocument();
});
