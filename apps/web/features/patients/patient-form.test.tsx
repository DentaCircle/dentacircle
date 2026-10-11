import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { EditPatientScreen } from "@/features/patients/edit-patient-screen";
import { PatientForm } from "@/features/patients/patient-form";

const push = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const patientId = "00000000-0000-4000-8000-000000000010";
const initial = { fullName: "Sample Ada", phone: "9000000001", dateOfBirth: "1990-04-05" };

afterEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

test("an edit starts from the current values and can clear the date of birth", async () => {
  const user = userEvent.setup();
  const fetchMock = stubFetch(jsonResponse(200, { id: patientId }));
  render(<PatientForm mode="edit" patientId={patientId} initial={initial} />);

  expect(screen.getByLabelText("Name")).toHaveValue("Sample Ada");
  expect(screen.getByLabelText("Phone")).toHaveValue("9000000001");
  expect(screen.getByLabelText("Date of birth (optional)")).toHaveValue("1990-04-05");
  await user.clear(screen.getByLabelText("Date of birth (optional)"));
  await user.click(screen.getByRole("button", { name: "Save patient" }));

  expect(fetchMock).toHaveBeenCalledWith(`/api/patients/${patientId}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      full_name: "Sample Ada",
      phone: "9000000001",
      date_of_birth: null,
    }),
  });
  expect(push).toHaveBeenCalledWith(`/patients/${patientId}?saved=1`);
  expect(refresh).toHaveBeenCalledOnce();
});

test("shows a 422 next to the named field", async () => {
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
  render(<PatientForm mode="edit" patientId={patientId} initial={initial} />);

  await user.clear(screen.getByLabelText("Phone"));
  await user.type(screen.getByLabelText("Phone"), "12");
  await user.click(screen.getByRole("button", { name: "Save patient" }));

  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("Enter 7 to 15 digits.");
  expect(alert.textContent).not.toContain("12");
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
  render(<PatientForm mode="edit" patientId={patientId} initial={initial} />);

  const button = screen.getByRole("button", { name: "Save patient" });
  const first = user.click(button);
  const second = user.click(button);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  resolveFetch(jsonResponse(200, {}));
  await Promise.all([first, second]);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("hides the form when the role cannot edit", () => {
  render(<EditPatientScreen canEdit={false} />);

  expect(screen.getByRole("alert")).toHaveTextContent("You do not have access.");
  expect(screen.queryByRole("button", { name: "Save patient" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
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
