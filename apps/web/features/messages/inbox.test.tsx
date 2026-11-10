import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { Inbox } from "@/features/messages/inbox";

afterEach(() => vi.unstubAllGlobals());

test("shows the latest message and refreshes", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => String(input).includes("connection")
    ? Response.json({status: "connected", can_send_text: true})
    : Response.json({items: [{patient: {id: "p1", display_id: "P-0001", full_name: "Synthetic Person", status: "active"}, latest_message: {origin: "provider", state: "received", body: "<b>literal</b>", created_at: "2026-01-01T00:00:00Z"}, message_count: 1}], total: 1, page: 1, page_size: 20}));
  vi.stubGlobal("fetch", fetcher);
  render(<Inbox timezone="Asia/Kolkata" />);
  expect(await screen.findByText("<b>literal</b>")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: /Synthetic Person/})).toHaveAttribute("href", "/patients/p1/messages");
  await userEvent.click(screen.getByRole("button", {name: "Refresh"}));
  expect(fetcher).toHaveBeenCalledTimes(4);
});

test("reports a refused inbox", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, {status: 403})));
  render(<Inbox timezone="Asia/Kolkata" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("You do not have access to messages.");
});
