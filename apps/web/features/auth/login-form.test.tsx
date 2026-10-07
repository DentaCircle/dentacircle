import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { LoginForm } from "@/features/auth/login-form";

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

test("posts credentials and goes to the dashboard on success", async () => {
  const user = userEvent.setup();
  const fetchMock = stubFetch(jsonResponse(200, { user: { full_name: "should-not-be-shown" } }));
  render(<LoginForm />);

  await user.type(screen.getByLabelText("Email"), "a@x.test");
  await user.type(screen.getByLabelText("Password"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Sign in" }));

  expect(fetchMock).toHaveBeenCalledWith("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ email: "a@x.test", password: "secret-value" }),
  });
  expect(push).toHaveBeenCalledWith("/");
  expect(refresh).toHaveBeenCalledOnce();
  expect(screen.queryByText("should-not-be-shown")).not.toBeInTheDocument();
});

test("shows a fixed message for a wrong password and clears only the password", async () => {
  await expectFailure(401, "Email or password is wrong.", { email: "nobody@x.test", password: "wrong-password" });
});

test("shows a fixed message when the API rejects the body", async () => {
  await expectFailure(422, "Enter an email and password.", { email: "a@x.test", password: "typed-password" });
});

test("shows a fixed message when the API cannot be reached", async () => {
  const user = userEvent.setup();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("failed"))));
  render(<LoginForm />);

  await user.type(screen.getByLabelText("Email"), "a@x.test");
  await user.type(screen.getByLabelText("Password"), "secret-value");
  await user.click(screen.getByRole("button", { name: "Sign in" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server.");
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.getByRole("alert").textContent).not.toContain("a@x.test");
  expect(screen.getByRole("alert").textContent).not.toContain("secret-value");
  expect(push).not.toHaveBeenCalled();
});

test("disables the button while the request is in flight", async () => {
  const user = userEvent.setup();
  let resolveFetch: (value: unknown) => void = () => undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    ),
  );
  render(<LoginForm />);

  await user.type(screen.getByLabelText("Email"), "a@x.test");
  await user.type(screen.getByLabelText("Password"), "secret-value");
  const pending = user.click(screen.getByRole("button", { name: "Sign in" }));

  await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled());
  resolveFetch(jsonResponse(401, { error: { message: "secret-value" } }));
  await pending;
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});

async function expectFailure(
  status: number,
  message: string,
  typed: { email: string; password: string },
): Promise<void> {
  const user = userEvent.setup();
  stubFetch(jsonResponse(status, { error: { message: typed.password, email: typed.email } }));
  render(<LoginForm />);

  await user.type(screen.getByLabelText("Email"), typed.email);
  await user.type(screen.getByLabelText("Password"), typed.password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));

  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent(message);
  expect(alert.textContent).not.toContain(typed.email);
  expect(alert.textContent).not.toContain(typed.password);
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.getByLabelText("Email")).toHaveValue(typed.email);
  expect(push).not.toHaveBeenCalled();
}

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
