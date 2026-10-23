import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { UploadForm } from "@/features/documents/upload-form";
import { MAX_UPLOAD_BYTES } from "@/features/documents/sizes";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const PATIENT = "patient-1";

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function pdf(name = "report.pdf"): File {
  return new File(["%PDF-1.7 synthetic"], name, { type: "application/pdf" });
}

function errorResponse(status: number, code: string) {
  return {
    ok: false,
    status,
    json: () =>
      Promise.resolve({ error: { code, message: "server text", request_id: "req-1" } }),
  };
}

function setup() {
  // The picker filters by `accept` by default. The wrong-type test needs to pass a bad file in.
  return userEvent.setup({ applyAccept: false });
}

test("sends the file as the raw body, with its type and a 60 second timeout", async () => {
  const user = setup();
  const timeout = vi.spyOn(AbortSignal, "timeout");
  const fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);
  const file = pdf("My report.pdf");

  await user.upload(screen.getByLabelText("File"), file);
  await user.click(screen.getByRole("button", { name: "Upload" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/patients/patient-1/documents?filename=My%20report.pdf",
    expect.objectContaining({
      method: "POST",
      body: file,
      headers: { "content-type": "application/pdf" },
      credentials: "same-origin",
    }),
  );
  expect(timeout).toHaveBeenCalledWith(60_000);
  await waitFor(() =>
    expect(push).toHaveBeenCalledWith("/patients/patient-1/documents?page=1&notice=uploaded"),
  );
  expect(refresh).toHaveBeenCalled();
});

test("a file name with special characters is encoded in the query", async () => {
  const user = setup();
  const fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);

  await user.upload(screen.getByLabelText("File"), pdf("a&b=c#d.pdf"));
  await user.click(screen.getByRole("button", { name: "Upload" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const calls = fetchMock.mock.calls as unknown as [string][];
  expect(calls[0][0]).toBe("/api/patients/patient-1/documents?filename=a%26b%3Dc%23d.pdf");
});

test("no file is a message and sends nothing", async () => {
  const user = setup();
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);

  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Choose a file first.");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a wrong type, an empty file and a file over 8 MB are refused before sending", async () => {
  const user = setup();
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);
  const input = screen.getByLabelText("File");
  const button = screen.getByRole("button", { name: "Upload" });

  await user.upload(input, new File(["GIF89a"], "pic.gif", { type: "image/gif" }));
  await user.click(button);
  expect(screen.getByRole("alert")).toHaveTextContent("Only PDF, PNG and JPEG files are allowed.");

  await user.upload(input, new File([], "empty.pdf", { type: "application/pdf" }));
  await user.click(button);
  expect(screen.getByRole("alert")).toHaveTextContent("That file is empty.");

  const big = pdf("big.pdf");
  Object.defineProperty(big, "size", { value: MAX_UPLOAD_BYTES + 1 });
  await user.upload(input, big);
  await user.click(button);
  expect(screen.getByRole("alert")).toHaveTextContent("That file is too large. The limit is 8 MB.");

  expect(fetchMock).not.toHaveBeenCalled();
  expect(push).not.toHaveBeenCalled();
});

test.each([
  [413, "payload_too_large", "That file is too large. The limit is 8 MB."],
  [415, "unsupported_media_type", "Only PDF, PNG and JPEG files are allowed."],
  [409, "patient_inactive", "This patient is inactive."],
  [403, "forbidden", "You do not have access."],
])("an API %i shows its fixed text and stays on the page", async (status, code, text) => {
  const user = setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(errorResponse(status, code))));
  render(<UploadForm patientId={PATIENT} />);

  await user.upload(screen.getByLabelText("File"), pdf());
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(text);
  expect(screen.getByRole("alert")).not.toHaveTextContent("server text");
  expect(push).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
});

test("a network error and a timeout each show fixed text", async () => {
  const user = setup();
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockRejectedValueOnce(new DOMException("timed out", "TimeoutError"));
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);
  await user.upload(screen.getByLabelText("File"), pdf());

  await user.click(screen.getByRole("button", { name: "Upload" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The upload could not reach the server. Try again.",
  );

  await user.click(screen.getByRole("button", { name: "Upload" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("The upload took too long. Try again."),
  );
  expect(push).not.toHaveBeenCalled();
});

test("a second click while the upload is running sends nothing more", async () => {
  const user = setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadForm patientId={PATIENT} />);
  await user.upload(screen.getByLabelText("File"), pdf());
  const button = screen.getByRole("button", { name: "Upload" });

  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  resolveFetch({ ok: true, status: 201, json: () => Promise.resolve({}) });
  await Promise.all([first, second]);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
});

test("the file picker only offers the three types", () => {
  render(<UploadForm patientId={PATIENT} />);
  const accept = screen.getByLabelText("File").getAttribute("accept") ?? "";
  expect(accept).toContain("application/pdf");
  expect(accept).toContain("image/png");
  expect(accept).toContain("image/jpeg");
});
