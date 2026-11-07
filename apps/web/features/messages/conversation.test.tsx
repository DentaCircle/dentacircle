import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { Conversation } from "@/features/messages/conversation";

const patientId = "00000000-0000-4000-8000-000000000001";
function setup(status = "active", body = "<b>not markup</b>") {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (init?.method === "POST") throw new Error("network failed");
    if (path.endsWith("/messaging-contact")) return Response.json({ id: "contact", patient_id: patientId, number: "+15551234567" });
    if (path.includes("/messages?")) return Response.json({ items: [{ id: "message", patient_id: patientId, direction: "inbound", origin: "provider", state: "received", body, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", provider_sent_at: null, created_by: null }], total: 1, page: 1, page_size: 20 });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "connected", can_send_text: true });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  return fetcher;
}

afterEach(() => vi.unstubAllGlobals());

test("renders incoming content literally and refreshes history", async () => {
  const fetcher = setup();
  expect(await screen.findByText("<b>not markup</b>")).toBeInTheDocument();
  expect(document.querySelector("b")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/messages?")).length).toBe(2));
});

test("uncertain sends reuse the request id for the same submission", async () => {
  const fetcher = setup();
  const input = await screen.findByLabelText("Message");
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("uncertain");
  expect(screen.getByLabelText("Message")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const posts = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2);
  const first = JSON.parse(String(posts[0][1]?.body));
  const second = JSON.parse(String(posts[1][1]?.body));
  expect(first).toMatchObject({ body: "Hello", request_id: expect.any(String) });
  expect(second).toEqual(first);
});

test("sending from a later page reloads page one and ignores an older page response", async () => {
  let resolveOldPage: ((response: Response) => void) | undefined;
  let resolveOldPageRead: (() => void) | undefined;
  const oldPageRead = new Promise<void>((resolve) => { resolveOldPageRead = resolve; });
  let pageOneLoads = 0;
  const oldPage = new Promise<Response>((resolve) => { resolveOldPage = resolve; });
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (init?.method === "POST") return Response.json({ id: "sent", patient_id: patientId, direction: "outbound", origin: "staff", state: "accepted", body: "Hello", created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z", provider_sent_at: null, created_by: { id: "staff", name: "Synthetic Staff" } }, { status: 201 });
    if (path.includes("/messages?page=2")) return oldPage;
    if (path.includes("/messages?")) {
      pageOneLoads += 1;
      const body = pageOneLoads === 1 ? "Initial history" : "Newest message";
      return Response.json({
        items: [{ id: `page-one-${pageOneLoads}`, patient_id: patientId, direction: "outbound", origin: "staff", state: "accepted", body, created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z", provider_sent_at: null, created_by: { id: "staff", name: "Synthetic Staff" } }],
        total: 21, page: 1, page_size: 20,
      });
    }
    if (path.endsWith("/messaging-contact")) return Response.json({ id: "contact", patient_id: patientId, number: "+15551234567" });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "connected", can_send_text: true });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status: "active" });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  await userEvent.click(await screen.findByRole("button", { name: "Next" }));
  await userEvent.type(await screen.findByLabelText("Message"), "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => {
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(pageOneLoads).toBe(2);
  });
  expect(await screen.findByText("Newest message")).toBeInTheDocument();
  await act(async () => {
    const staleResponse = Response.json({
      items: [{ id: "old", patient_id: patientId, direction: "inbound", origin: "provider", state: "received", body: "Older page", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", provider_sent_at: null, created_by: null }],
      total: 21, page: 2, page_size: 20,
    });
    const readJson = staleResponse.json.bind(staleResponse);
    Object.defineProperty(staleResponse, "json", {
      value: async () => {
        const data = await readJson();
        resolveOldPageRead?.();
        return data;
      },
    });
    resolveOldPage?.(staleResponse);
    await oldPage;
    await oldPageRead;
    await Promise.resolve();
  });
  expect(screen.getByText("Newest message")).toBeInTheDocument();
  expect(screen.queryByText("Older page")).not.toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/messages?page=1"))).toHaveLength(2);
});

test.each(["sending", "unknown"])("keeps the same request after a %s replay", async (state) => {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (init?.method === "POST") {
      return Response.json({ id: "attempt", patient_id: patientId, direction: "outbound", state, body: "Hello", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", provider_sent_at: null, created_by: null });
    }
    if (path.endsWith("/messaging-contact")) return Response.json({ id: "contact", patient_id: patientId, number: "+15551234567" });
    if (path.includes("/messages?")) return Response.json({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "connected", can_send_text: true });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status: "active" });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  const input = await screen.findByLabelText("Message");
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("uncertain");
  expect(input).toHaveValue("Hello");
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const posts = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(JSON.parse(String(posts[1][1]?.body))).toEqual(JSON.parse(String(posts[0][1]?.body)));
});

test("inactive patients can read history but cannot send", async () => {
  setup("inactive");
  expect(await screen.findByText(/This patient is inactive/)).toBeInTheDocument();
  expect(screen.getByText("<b>not markup</b>")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
});

test("a double click dispatches only one request", async () => {
  const fetcher = setup();
  const input = await screen.findByLabelText("Message");
  await userEvent.type(input, "Hello");
  const button = screen.getByRole("button", { name: "Send" });
  await userEvent.dblClick(button);
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
});

test("unlinked and disconnected patients cannot send", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/messaging-contact")) return Response.json(null);
    if (path.includes("/messages?")) return Response.json({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "disconnected", can_send_text: false });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status: "active" });
  }));
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  expect(await screen.findByText(/Connection: disconnected/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Link number" })).toBeInTheDocument();
  expect(screen.getByText("No messages yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
});

test("shows a no-access state when the API refuses the patient", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 403 })));
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("You do not have access to messages.");
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
});

test("accepts 2,000 Unicode characters and rejects longer text", async () => {
  const fetcher = setup();
  const input = await screen.findByLabelText("Message");
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: "😀".repeat(2001) } });
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter 1 to 2,000 characters.");
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  fireEvent.change(input, { target: { value: "😀".repeat(2000) } });
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const posts = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(1);
  expect(JSON.parse(String(posts[0][1]?.body)).body).toBe("😀".repeat(2000));
});

test("previews a clinic invitation and sends it with its own purpose", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (init?.method === "POST") return Response.json({ id: "sent", patient_id: patientId,
      direction: "outbound", origin: "staff", state: "accepted", body: "invitation",
      created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z",
      provider_sent_at: null, created_by: { id: "staff", name: "Synthetic Staff" } }, { status: 201 });
    if (path.endsWith("/messaging-contact")) return Response.json({ id: "contact", patient_id: patientId,
      number: "+15551234567", automation_state: "needs_staff" });
    if (path.includes("/messages?")) return Response.json({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "connected", can_send_text: true });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status: "active" });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  expect(await screen.findByText("Handling: Needs reception")).toBeInTheDocument();
  expect(screen.getByText("Hello from Synthetic Clinic. Reply BOOK to choose an appointment time.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Send booking invitation" }));
  const post = fetcher.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
    body: "Hello from Synthetic Clinic. Reply BOOK to choose an appointment time.",
    purpose: "booking_invitation", request_id: expect.any(String),
  });
});

test("staff can take over and resume booking", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.endsWith("/messaging-automation") && init?.method === "PUT") {
      const state = JSON.parse(String(init.body)).state;
      return Response.json({ id: "contact", patient_id: patientId, number: "+15551234567", automation_state: state });
    }
    if (path.endsWith("/messaging-contact")) return Response.json({ id: "contact", patient_id: patientId,
      number: "+15551234567", automation_state: "needs_staff" });
    if (path.includes("/messages?")) return Response.json({ items: [], total: 0, page: 1, page_size: 20 });
    if (path.endsWith("/messaging/connection")) return Response.json({ status: "connected", can_send_text: true });
    return Response.json({ id: patientId, full_name: "Synthetic Example", display_id: "P-0001", status: "active" });
  });
  vi.stubGlobal("fetch", fetcher);
  render(<Conversation patientId={patientId} timezone="Asia/Kolkata" clinicName="Synthetic Clinic" />);
  expect(await screen.findByText("Handling: Needs reception")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Take over" }));
  expect(await screen.findByText("Handling: Reception handling")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Resume booking" }));
  expect(await screen.findByText("Handling: Booking available")).toBeInTheDocument();
  const requests = fetcher.mock.calls.filter(([path]) => String(path).endsWith("/messaging-automation"));
  expect(requests.map(([, init]) => JSON.parse(String(init?.body)).state)).toEqual(["staff_handling", "active"]);
});

test("an uncertain invitation reuses its request id after refresh", async () => {
  const fetcher = setup();
  await userEvent.click(await screen.findByRole("button", { name: "Send booking invitation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("uncertain");
  expect(screen.getByRole("button", { name: "Send booking invitation" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await userEvent.click(screen.getByRole("button", { name: "Send booking invitation" }));
  const posts = fetcher.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2);
  const first = JSON.parse(String(posts[0][1]?.body));
  const second = JSON.parse(String(posts[1][1]?.body));
  expect(first.purpose).toBe("booking_invitation");
  expect(second).toEqual(first);
});
