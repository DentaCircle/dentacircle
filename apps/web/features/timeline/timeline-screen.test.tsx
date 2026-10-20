import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { TimelineScreen, type TimelineDayGroup } from "@/features/timeline/timeline-screen";

const patientId = "00000000-0000-4000-8000-000000000010";

test("shows entries, the actor and a page link", () => {
  render(
    <TimelineScreen
      status="ready"
      patientId={patientId}
      days={[day]}
      page={2}
      pageSize={20}
      total={41}
    />,
  );

  expect(screen.getByRole("heading", { name: "Mon 12 Oct" })).toBeInTheDocument();
  expect(screen.getByText("10:00")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Visit completed: Scaling with Dr Rao" })).toHaveAttribute(
    "href",
    "/calendar?view=day&date=2026-10-12",
  );
  expect(screen.getByText("Dr Rao")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
    "href",
    `/patients/${patientId}/timeline?page=1`,
  );
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
    "href",
    `/patients/${patientId}/timeline?page=3`,
  );
});

test("shows the empty, no-access, not-found and error states", () => {
  const { rerender } = render(<TimelineScreen {...blank("empty")} />);
  expect(screen.getByText("Nothing has happened for this patient yet.")).toBeInTheDocument();

  rerender(<TimelineScreen {...blank("forbidden")} />);
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");

  rerender(<TimelineScreen {...blank("not-found")} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");

  rerender(<TimelineScreen {...blank("error")} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Timeline could not be loaded.");
});

const day: TimelineDayGroup = {
  date: "2026-10-12",
  heading: "Mon 12 Oct",
  entries: [
    {
      id: "event-1",
      time: "10:00",
      sentence: "Visit completed: Scaling with Dr Rao",
      actorName: "Dr Rao",
      href: "/calendar?view=day&date=2026-10-12",
    },
  ],
};

function blank(status: "empty" | "forbidden" | "not-found" | "error") {
  return {
    status,
    patientId,
    days: [],
    page: 1,
    pageSize: 20,
    total: 0,
  };
}
