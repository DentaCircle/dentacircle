import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { NewPatientForm } from "@/features/patients/new-patient-form";
import { NewPatientScreen } from "@/features/patients/new-patient-screen";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("saves a patient and shows the new id on the list", async () => {
  const user = userEvent.setup();
  const fetchMock = stubFetch(
    jsonResponse(201, {
      display_id: "P-0001",
      full_name: "Sample Ada",
      phone: "9000000001",
    }),
  );
  render(<NewPatientForm />);

  await user.type(screen.getByLabelText("Name"), "Sample Ada");
  await user.type(screen.getByLabelText("Phone"), "9000000001");
  await user.type(screen.getByLabelText("Date of birth (optional)"), "1990-04-05");
  await user.click(screen.getByRole("button", { name: "Save patient" }));

  expect(fetchMock).toHaveBeenCalledWith("/api/patients", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      full_name: "Sample Ada",
      phone: "9000000001",
      date_of_birth: "1990-04-05",
    }),
  });
  expect(push).toHaveBeenCalledWith("/patients?created=P-0001");
  expect(refresh).toHaveBeenCalledOnce();
  expect(screen.queryByText("P-0001")).not.toBeInTheDocument();
});

test("shows a 422 next to the named field and not the submitted value", async () => {
  const user = userEvent.setup();
  stubFetch(
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "body.phone: phone_digits",
        request_id: "req-1",
      },
    }),
  );
  render(<NewPatientForm />);

  await user.type(screen.getByLabelText("Name"), "Sample Ada");
  await user.type(screen.getByLabelText("Phone"), "12");
  await user.click(screen.getByRole("button", { name: "Save patient" }));

  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("Enter 7 to 15 digits.");
  expect(alert.textContent).not.toContain("12");
  expect(screen.getByLabelText("Phone")).toHaveAttribute("aria-describedby", "phone-error");
  expect(push).not.toHaveBeenCalled();
});

test("a double click sends one request", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  const fetchMock = vi.fn(
    () =>
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<NewPatientForm />);

  await user.type(screen.getByLabelText("Name"), "Sample Ada");
  await user.type(screen.getByLabelText("Phone"), "9000000001");
  const button = screen.getByRole("button", { name: "Save patient" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  resolveFetch(jsonResponse(201, { display_id: "P-0001" }));
  await Promise.all([first, second]);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("hides the form when the role cannot create", () => {
  render(<NewPatientScreen canCreate={false} />);

  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByRole("button", { name: "Save patient" })).not.toBeInTheDocument();
});

function jsonResponse(status: number, body: unknown): { ok: boolean; status: number; json: () => Promise<unknown> } {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}

function stubFetch(value: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(() => Promise.resolve(value));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
