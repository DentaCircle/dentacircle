import type { ApiError } from "@/lib/api/errors";

export type InventoryNotice =
  | "category-added"
  | "category-renamed"
  | "item-added"
  | "item-updated"
  | "deactivated"
  | "reactivated"
  | "batch-added"
  | "batch-updated"
  | "stock-added"
  | "stock-adjusted";

export const INVENTORY_NOTICES: Record<InventoryNotice, string> = {
  "category-added": "Category added.",
  "category-renamed": "Category renamed.",
  "item-added": "Item added.",
  "item-updated": "Item updated.",
  deactivated: "Item deactivated.",
  reactivated: "Item reactivated.",
  "batch-added": "Batch added.",
  "batch-updated": "Batch updated.",
  "stock-added": "Stock added.",
  "stock-adjusted": "Stock adjusted.",
};

const NOTICES = new Set<string>(Object.keys(INVENTORY_NOTICES));

export function isInventoryNotice(value: string | undefined): value is InventoryNotice {
  return value !== undefined && NOTICES.has(value);
}

export const ENTER_A_NAME = "Enter a name.";
export const ENTER_A_UNIT = "Enter a unit.";
export const ENTER_A_BATCH = "Enter a batch number.";
export const CHOOSE_A_CATEGORY = "Choose a category.";
export const CHECK_THE_THRESHOLD = "Enter a whole number from 0 to 1,000,000.";
export const CHECK_THE_DATE = "Choose a date from 1 Jan 2000 through 20 years ahead.";
export const NAME_TAKEN = "That name is already in use.";
export const BATCH_TAKEN = "That batch number is already in use.";
export const ITEM_INACTIVE = "This item is inactive. New batches cannot be added.";
export const ALREADY_THAT_STATUS = "This item already has that status.";
export const ENTER_A_QUANTITY = "Enter a whole number from 1 to 1,000,000.";
export const ENTER_A_CHANGE = "Enter a non-zero whole number up to 1,000,000.";
export const NEGATIVE_CHANGE = "Damaged and expired adjustments must remove stock.";
export const CHOOSE_A_REASON = "Choose damaged, expired or correction.";
export const INSUFFICIENT_STOCK = "There is not enough stock.";
export const NOT_FOUND = "Not found.";
export const NO_ACCESS = "You do not have access.";
export const CHECK_THE_FORM = "Check the form.";

const FIELD_TEXT: Record<string, string> = {
  "body.name:string_too_short": ENTER_A_NAME,
  "body.name:string_too_long": "Use a shorter name.",
  "body.name:missing": ENTER_A_NAME,
  "body.unit:string_too_short": ENTER_A_UNIT,
  "body.unit:string_too_long": "Use a shorter unit.",
  "body.unit:missing": ENTER_A_UNIT,
  "body.category_id:missing": CHOOSE_A_CATEGORY,
  "body.category_id:uuid_parsing": CHOOSE_A_CATEGORY,
  "body.low_stock_threshold:int_type": CHECK_THE_THRESHOLD,
  "body.low_stock_threshold:int_parsing": CHECK_THE_THRESHOLD,
  "body.low_stock_threshold:greater_than_equal": CHECK_THE_THRESHOLD,
  "body.low_stock_threshold:less_than_equal": CHECK_THE_THRESHOLD,
  "body.batch_number:string_too_short": ENTER_A_BATCH,
  "body.batch_number:string_too_long": "Use a shorter batch number.",
  "body.expiry_on:before_2000": CHECK_THE_DATE,
  "body.expiry_on:beyond_horizon": CHECK_THE_DATE,
  "body.expiry_on:date_from_datetime_parsing": CHECK_THE_DATE,
  "body.expiry_on:date_parsing": CHECK_THE_DATE,
  "body.quantity:int_type": ENTER_A_QUANTITY,
  "body.quantity:int_parsing": ENTER_A_QUANTITY,
  "body.quantity:greater_than_equal": ENTER_A_QUANTITY,
  "body.quantity:less_than_equal": ENTER_A_QUANTITY,
  "body.quantity_change:int_type": ENTER_A_CHANGE,
  "body.quantity_change:int_parsing": ENTER_A_CHANGE,
  "body.quantity_change:greater_than_equal": ENTER_A_CHANGE,
  "body.quantity_change:less_than_equal": ENTER_A_CHANGE,
  "body.quantity_change:must_be_negative": NEGATIVE_CHANGE,
  "body.reason:literal_error": CHOOSE_A_REASON,
};

export type FieldMessages = { form: string | null; fields: Record<string, string> };

/** Fixed text only. A submitted name, unit or batch number is never shown. */
export function inventoryFailure(error: ApiError): FieldMessages {
  if (error.kind === "timeout") {
    return { form: "The change took too long. Try again.", fields: {} };
  }
  if (error.kind === "network") {
    return { form: "The change could not reach the server. Try again.", fields: {} };
  }
  if (error.status === 409 && error.code === "duplicate_name") {
    return { form: NAME_TAKEN, fields: {} };
  }
  if (error.status === 409 && error.code === "duplicate_batch") {
    return { form: BATCH_TAKEN, fields: {} };
  }
  if (error.status === 409 && error.code === "item_inactive") {
    return { form: ITEM_INACTIVE, fields: {} };
  }
  if (error.status === 409 && error.code === "invalid_status") {
    return { form: ALREADY_THAT_STATUS, fields: {} };
  }
  if (error.status === 409 && error.code === "insufficient_stock") {
    return { form: INSUFFICIENT_STOCK, fields: {} };
  }
  if (error.status === 403) return { form: NO_ACCESS, fields: {} };
  if (error.status === 404) return { form: NOT_FOUND, fields: {} };
  if (error.status === 422) return fieldMessages(error.message);
  return { form: "Something went wrong.", fields: {} };
}

function fieldMessages(message: string): FieldMessages {
  const fields: Record<string, string> = {};
  for (const part of message.split("; ")) {
    const [location, code] = part.split(": ");
    if (location === undefined || code === undefined) continue;
    const text = FIELD_TEXT[`${location}:${code}`];
    const name = location.startsWith("body.") ? location.slice("body.".length) : "";
    if (text !== undefined && name !== "") fields[name] = text;
  }
  if (Object.keys(fields).length === 0) return { form: CHECK_THE_FORM, fields: {} };
  return { form: null, fields };
}
