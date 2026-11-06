import { expect, test } from "vitest";
import type { components } from "@/lib/api/schema";
import { messageActor, messageState } from "./message-labels";

type Message = components["schemas"]["MessageBody"];

function message(overrides: Partial<Message>): Message {
  return { id: "1", patient_id: "p", direction: "outbound", origin: "staff", body: "Hello",
    state: "accepted", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    provider_sent_at: null, created_by: { id: "s", name: "Synthetic Staff" }, ...overrides };
}

test("labels message origins and honest send states", () => {
  expect(messageActor(message({ origin: "provider", direction: "inbound", created_by: null }))).toBe("Patient via WhatsApp");
  expect(messageActor(message({ origin: "automation", created_by: null }))).toBe("Automatic reply");
  expect(messageActor(message({}))).toBe("Synthetic Staff");
  expect(messageState(message({ state: "queued" }))).toBe("Queued");
  expect(messageState(message({ state: "superseded" }))).toBe("Not sent");
  expect(messageState(message({ state: "unknown" }))).toBe("Send outcome unconfirmed");
  expect(messageState(message({ state: "sending" }))).toBe("Send outcome unconfirmed");
});
