import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { HistoryPanel } from "@/features/inventory/history-panel";
import {
  ENTER_A_RULE_QUANTITY,
  RULE_INACTIVE,
  RULE_NOT_FOUND,
} from "@/features/inventory/rules-forms";
import { RulesScreen } from "@/features/inventory/rules-screen";
import { historyEntry } from "@/features/inventory/rows";
import { removeResourceRule, saveResourceRule } from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/client", () => ({
  saveResourceRule: vi.fn(),
  removeResourceRule: vi.fn(),
}));

const items = [
  { id: "item-gloves", name: "Gloves M" },
  { id: "item-masks", name: "Masks" },
];

test("a writer sees rules, an empty type, and a quantity error", async () => {
  const user = userEvent.setup();
  render(
    <RulesScreen
      status="ready"
      canWrite
      notice={null}
      items={items}
      types={[
        {
          id: "scaling",
          name: "Scaling",
          rules: [{ itemId: "item-gloves", itemName: "Gloves M", quantity: 2 }],
        },
        { id: "consult", name: "Consultation", rules: [] },
      ]}
    />,
  );
  expect(screen.getByRole("heading", { name: "Scaling" })).toBeInTheDocument();
  expect(screen.getAllByText("Gloves M").length).toBeGreaterThan(0);
  expect(screen.getByText("No stock is used by this visit type.")).toBeInTheDocument();
  const form = screen.getByRole("form", { name: "Add a rule for Consultation" });
  await user.selectOptions(within(form).getByLabelText("Item"), "item-masks");
  await user.type(within(form).getByLabelText("Quantity"), "0");
  await user.click(within(form).getByRole("button", { name: "Add rule" }));
  expect(within(form).getByRole("alert")).toHaveTextContent(ENTER_A_RULE_QUANTITY);
  expect(saveResourceRule).not.toHaveBeenCalled();
});

test("a failed save shows fixed text for 404 and 409", async () => {
  const user = userEvent.setup();
  vi.mocked(saveResourceRule)
    .mockResolvedValueOnce({
      ok: false,
      error: { kind: "api", status: 409, code: "item_inactive", message: "hidden", requestId: "r" },
    })
    .mockResolvedValueOnce({
      ok: false,
      error: { kind: "api", status: 404, code: "not_found", message: "hidden", requestId: "r" },
    });
  render(
    <RulesScreen
      status="ready"
      canWrite
      notice={null}
      items={items}
      types={[
        {
          id: "scaling",
          name: "Scaling",
          rules: [{ itemId: "item-gloves", itemName: "Gloves M", quantity: 2 }],
        },
      ]}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(RULE_INACTIVE);
  await user.selectOptions(screen.getByLabelText("Item"), "item-masks");
  await user.type(screen.getByRole("form", { name: "Add a rule for Scaling" }).querySelector("input") as HTMLInputElement, "2");
  await user.click(screen.getByRole("button", { name: "Add rule" }));
  expect(await screen.findByText(RULE_NOT_FOUND)).toBeInTheDocument();
});

test("a clinician sees the rules and no edit controls", () => {
  render(
    <RulesScreen
      status="ready"
      canWrite={false}
      notice={null}
      items={items}
      types={[
        {
          id: "scaling",
          name: "Scaling",
          rules: [{ itemId: "item-gloves", itemName: "Gloves M", quantity: 2 }],
        },
      ]}
    />,
  );
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add rule" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
});

test("removing a rule calls the delete", async () => {
  const user = userEvent.setup();
  vi.mocked(removeResourceRule).mockResolvedValue({ ok: true, data: null });
  render(
    <RulesScreen
      status="ready"
      canWrite
      notice={null}
      items={items}
      types={[
        {
          id: "scaling",
          name: "Scaling",
          rules: [{ itemId: "item-gloves", itemName: "Gloves M", quantity: 2 }],
        },
      ]}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Remove" }));
  expect(removeResourceRule).toHaveBeenCalledWith("scaling", "item-gloves");
});

test("a consumption row links to the visit day", () => {
  const entry = historyEntry({
    id: "tx-1",
    type: "consumption",
    reason: null,
    quantity_change: -2,
    batch: { id: "batch-1", batch_number: "LOT-1" },
    recorded_by: "Sample Clinician",
    created_at: "2026-10-26T10:05:00+05:30",
    appointment_id: "visit-1",
    visit_on: "2026-10-26",
  });
  render(
    <HistoryPanel
      itemId="item-gloves"
      history={{ status: "ready", rows: [entry], total: 1, page: 1, pageSize: 20 }}
    />,
  );
  expect(screen.getByRole("link", { name: "Used in visit" })).toHaveAttribute(
    "href",
    "/calendar?view=day&date=2026-10-26",
  );
});
