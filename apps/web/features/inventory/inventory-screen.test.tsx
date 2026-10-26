import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { InventoryItemScreen } from "@/features/inventory/item-screen";
import { InventoryListScreen } from "@/features/inventory/list-screen";
import type { InventoryRow } from "@/features/inventory/rows";
import {
  adjustInventoryBatch,
  createInventoryBatch,
  createInventoryCategory,
  createInventoryItem,
  restockInventoryBatch,
  setInventoryItemStatus,
} from "@/lib/api/client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/api/client", () => ({
  createInventoryCategory: vi.fn(),
  renameInventoryCategory: vi.fn(),
  createInventoryItem: vi.fn(),
  updateInventoryItem: vi.fn(),
  setInventoryItemStatus: vi.fn(),
  createInventoryBatch: vi.fn(),
  updateInventoryBatch: vi.fn(),
  restockInventoryBatch: vi.fn(),
  adjustInventoryBatch: vi.fn(),
}));

const gloves: InventoryRow = {
  id: "item-1",
  name: "Gloves M",
  categoryName: "Consumables",
  unit: "box",
  threshold: 2,
  batchCount: 2,
  stock: 12,
  status: "active",
  statusLabel: "Active",
};

const categories = [{ id: "cat-1", name: "Consumables", itemCount: 1 }];

beforeEach(() => {
  vi.mocked(createInventoryItem).mockReset();
  vi.mocked(createInventoryBatch).mockReset();
  vi.mocked(createInventoryCategory).mockReset();
  vi.mocked(setInventoryItemStatus).mockReset();
});

test("the inventory page lists items and the status switch", () => {
  render(
    <InventoryListScreen
      status="ready"
      rows={[gloves]}
      categories={categories}
      total={1}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice="item-added"
      canWrite
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Item added.");
  expect(screen.getByRole("link", { name: "Gloves M" })).toHaveAttribute("href", "/inventory/item-1");
  expect(screen.getByRole("link", { name: "Inactive" })).toHaveAttribute(
    "href",
    "/inventory?status=inactive",
  );
  expect(screen.getByRole("columnheader", { name: "Stock" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "12" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add item" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add category" })).toBeInTheDocument();
});

test("an empty list says there are no inventory items yet", () => {
  render(
    <InventoryListScreen
      status="empty"
      rows={[]}
      categories={categories}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "inactive", categoryId: "", query: "" }}
      notice={null}
      canWrite
    />,
  );
  expect(screen.getByText("No inventory items yet.")).toBeInTheDocument();
});

test("the add form asks for a category before any exist", () => {
  render(
    <InventoryListScreen
      status="empty"
      rows={[]}
      categories={[]}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice={null}
      canWrite
    />,
  );
  expect(screen.getByText("Add a category first.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
});

test("a blank item name is a field error and is not sent", async () => {
  const user = userEvent.setup();
  render(
    <InventoryListScreen
      status="empty"
      rows={[]}
      categories={categories}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice={null}
      canWrite
    />,
  );
  await user.click(screen.getByRole("button", { name: "Add item" }));
  expect(screen.getByText("Enter a name.")).toBeInTheDocument();
  expect(createInventoryItem).not.toHaveBeenCalled();
});

test("a saved item clears the add form so the next one starts empty", async () => {
  const user = userEvent.setup();
  vi.mocked(createInventoryItem).mockResolvedValue({ ok: true, data: null });
  render(
    <InventoryListScreen
      status="ready"
      rows={[]}
      categories={categories}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice="item-added"
      canWrite
    />,
  );
  await user.type(screen.getByRole("textbox", { name: "Name" }), "Gauze");
  await user.selectOptions(screen.getByRole("combobox", { name: "Category" }), "cat-1");
  await user.type(screen.getByRole("textbox", { name: "Unit" }), "pack");
  await user.click(screen.getByRole("button", { name: "Add item" }));
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("");
  expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("");
  expect(screen.getByRole("textbox", { name: "Unit" })).toHaveValue("");
});

test("a failed load hides the write forms", () => {
  render(
    <InventoryListScreen
      status="error"
      rows={[]}
      categories={[]}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice={null}
      canWrite
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Inventory could not be loaded.");
  expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add category" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Search by name")).not.toBeInTheDocument();
});

test("a clinician sees the list without write forms", () => {
  render(
    <InventoryListScreen
      status="ready"
      rows={[gloves]}
      categories={categories}
      total={1}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice={null}
      canWrite={false}
    />,
  );
  expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add category" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
});

test("a receptionist is told they have no access", () => {
  render(
    <InventoryListScreen
      status="forbidden"
      rows={[]}
      categories={[]}
      total={0}
      page={1}
      pageSize={20}
      filter={{ status: "active", categoryId: "", query: "" }}
      notice={null}
      canWrite={false}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("the item page shows an expired badge and asks before deactivating", async () => {
  const user = userEvent.setup();
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[
        {
          id: "batch-1",
          batchNumber: "LOT-OLD",
          expiryOn: "2020-01-01",
          expiryLabel: "1 Jan 2020",
          expired: true,
          quantity: 4,
        },
        {
          id: "batch-2",
          batchNumber: "LOT-NEW",
          expiryOn: "2030-01-01",
          expiryLabel: "1 Jan 2030",
          expired: false,
          quantity: 8,
        },
      ]}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  expect(screen.getByText("Stock 12")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Quantity" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "4" })).toBeInTheDocument();
  expect(screen.getByText("Expired", { selector: "[data-slot='badge']" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm deactivation" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Deactivate" }));
  expect(screen.getByRole("button", { name: "Confirm deactivation" })).toBeInTheDocument();
});

test("deactivating once asks again the next time the item is active", async () => {
  const user = userEvent.setup();
  vi.mocked(setInventoryItemStatus).mockResolvedValue({ ok: true, data: null });
  const { rerender } = render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[]}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  await user.click(screen.getByRole("button", { name: "Deactivate" }));
  await user.click(screen.getByRole("button", { name: "Confirm deactivation" }));
  expect(await screen.findByRole("button", { name: "Deactivate" })).toBeInTheDocument();
  rerender(
    <InventoryItemScreen
      status="ready"
      item={{ ...gloves, status: "inactive", statusLabel: "Inactive" }}
      batches={[]}
      categories={categories}
      notice="deactivated"
      canWrite
    />,
  );
  rerender(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[]}
      categories={categories}
      notice="reactivated"
      canWrite
    />,
  );
  expect(screen.getByRole("button", { name: "Deactivate" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm deactivation" })).not.toBeInTheDocument();
});

test("an inactive item hides the add batch form", () => {
  render(
    <InventoryItemScreen
      status="ready"
      item={{ ...gloves, status: "inactive", statusLabel: "Inactive" }}
      batches={[]}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  expect(screen.getByText("This item is inactive. New batches cannot be added.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add batch" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
});

test("a duplicate batch shows the fixed conflict text", async () => {
  const user = userEvent.setup();
  vi.mocked(createInventoryBatch).mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 409, code: "duplicate_batch", message: "secret-lot", requestId: "r" },
  });
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[]}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  await user.type(screen.getByLabelText("Batch number"), "LOT-1");
  await user.click(screen.getByRole("button", { name: "Add batch" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That batch number is already in use.");
  expect(screen.queryByText("secret-lot")).not.toBeInTheDocument();
});

test("a clinician item page is read only", () => {
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[
        {
          id: "batch-1",
          batchNumber: "LOT-1",
          expiryOn: null,
          expiryLabel: "No expiry",
          expired: false,
          quantity: 12,
        },
      ]}
      categories={categories}
      notice={null}
      canWrite={false}
      history={{
        status: "ready",
        total: 1,
        page: 1,
        pageSize: 20,
        rows: [
          {
            id: "move-1",
            typeLabel: "Restock",
            reasonLabel: "—",
            changeLabel: "+12",
            batchNumber: "LOT-1",
            recordedBy: "Synthetic Stores",
            whenLabel: "25 Oct 2026, 14:30",
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("Stock 12")).toBeInTheDocument();
  expect(screen.getByText("Synthetic Stores")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save item" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add batch" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add stock" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Adjust" })).not.toBeInTheDocument();
});

test("a missing item says not found", () => {
  render(
    <InventoryItemScreen
      status="not-found"
      item={null}
      batches={[]}
      categories={[]}
      notice={null}
      canWrite={false}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Not found.");
});

const oneBatch = [
  {
    id: "batch-1",
    batchNumber: "LOT-1",
    expiryOn: null,
    expiryLabel: "No expiry",
    expired: false,
    quantity: 5,
  },
];

test("an empty history says there are no stock movements yet", () => {
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={oneBatch}
      categories={categories}
      notice={null}
      canWrite
      history={{ status: "empty", rows: [], total: 0, page: 1, pageSize: 20 }}
    />,
  );
  expect(screen.getByText("No stock movements yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add stock" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Adjust" })).toBeInTheDocument();
});

test("an inactive item hides add stock and still shows adjust", () => {
  render(
    <InventoryItemScreen
      status="ready"
      item={{ ...gloves, status: "inactive", statusLabel: "Inactive" }}
      batches={oneBatch}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  expect(screen.queryByRole("button", { name: "Add stock" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Adjust" })).toBeInTheDocument();
});

test("a blank add-stock quantity is a field error and is not sent", async () => {
  const user = userEvent.setup();
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={oneBatch}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  await user.click(screen.getByRole("button", { name: "Add stock" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Enter a whole number from 1 to 1,000,000.",
  );
  expect(restockInventoryBatch).not.toHaveBeenCalled();
});

test("insufficient stock shows the fixed message and hides the server text", async () => {
  const user = userEvent.setup();
  vi.mocked(adjustInventoryBatch).mockResolvedValue({
    ok: false,
    error: {
      kind: "api",
      status: 409,
      code: "insufficient_stock",
      message: "secret-424242",
      requestId: "r",
    },
  });
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={oneBatch}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  await user.type(screen.getByLabelText("Quantity change"), "-100");
  await user.selectOptions(screen.getByLabelText("Reason"), "damaged");
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("There is not enough stock.");
  expect(screen.queryByText("secret-424242")).not.toBeInTheDocument();
});

test("a missing batch shows not found", async () => {
  const user = userEvent.setup();
  vi.mocked(restockInventoryBatch).mockResolvedValue({
    ok: false,
    error: { kind: "api", status: 404, code: "not_found", message: "secret-id", requestId: "r" },
  });
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={oneBatch}
      categories={categories}
      notice={null}
      canWrite
    />,
  );
  await user.type(screen.getByLabelText("Quantity"), "50");
  await user.click(screen.getByRole("button", { name: "Add stock" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  expect(screen.queryByText("secret-id")).not.toBeInTheDocument();
});

test("history pages when there is another page", () => {
  render(
    <InventoryItemScreen
      status="ready"
      item={gloves}
      batches={[]}
      categories={categories}
      notice={null}
      canWrite={false}
      history={{
        status: "ready",
        total: 21,
        page: 1,
        pageSize: 20,
        rows: [
          {
            id: "move-1",
            typeLabel: "Adjustment",
            reasonLabel: "Damaged",
            changeLabel: "-5",
            batchNumber: "LOT-1",
            recordedBy: "Synthetic Stores",
            whenLabel: "25 Oct 2026, 15:00",
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
    "href",
    "/inventory/item-1?page=2",
  );
});
