import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { requireUser, redirectIfSignedIn } from "@/features/auth/current-user";
import { getCurrentUser } from "@/lib/api/client";

vi.mock("next/headers", () => ({
  cookies: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn((path: string): never => {
    throw new Error(`redirect:${path}`);
  }),
}));

vi.mock("@/lib/api/client", () => ({
  getCurrentUser: vi.fn(),
}));

const syntheticUser = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "a@x.test",
  full_name: "Synthetic Person",
  roles: ["clinician"],
  clinic: { id: "00000000-0000-4000-8000-000000000002", name: "Synthetic Clinic" },
};

beforeEach(() => {
  vi.mocked(cookies).mockResolvedValue(cookieStore("session-token") as Awaited<ReturnType<typeof cookies>>);
  vi.mocked(redirect).mockClear();
  vi.mocked(getCurrentUser).mockReset();
});

describe("requireUser", () => {
  test("forwards the dc_session cookie and returns the user", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({ ok: true, data: syntheticUser });

    await expect(requireUser()).resolves.toEqual(syntheticUser);
    expect(getCurrentUser).toHaveBeenCalledWith("dc_session=session-token");
    expect(redirect).not.toHaveBeenCalled();
  });

  test("redirects to login when the API returns 401", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      ok: false,
      error: { kind: "api", status: 401, code: "unauthenticated", message: "Sign in required.", requestId: "req-1" },
    });

    await expect(requireUser()).rejects.toThrow("redirect:/login");
    expect(redirect).toHaveBeenCalledWith("/login");
  });

  test("throws and does not redirect when the API cannot be reached", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      ok: false,
      error: { kind: "network", message: "The API could not be reached." },
    });

    await expect(requireUser()).rejects.toThrow("The page could not be shown.");
    expect(redirect).not.toHaveBeenCalled();
  });

  test("throws and does not redirect when the body is unreadable", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      ok: false,
      error: { kind: "api", status: 200, code: "invalid_response", message: "The response could not be read.", requestId: "" },
    });

    await expect(requireUser()).rejects.toThrow("The page could not be shown.");
    expect(redirect).not.toHaveBeenCalled();
  });
});

describe("redirectIfSignedIn", () => {
  test("redirects to the dashboard when a session is valid", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({ ok: true, data: syntheticUser });

    await expect(redirectIfSignedIn()).rejects.toThrow("redirect:/");
    expect(redirect).toHaveBeenCalledWith("/");
  });

  test("stays on the page when the API returns 401", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      ok: false,
      error: { kind: "api", status: 401, code: "unauthenticated", message: "Sign in required.", requestId: "req-1" },
    });

    await expect(redirectIfSignedIn()).resolves.toBeUndefined();
    expect(redirect).not.toHaveBeenCalled();
  });
});

function cookieStore(value: string | undefined): { get: (name: string) => { name: string; value: string } | undefined } {
  return {
    get(name: string) {
      if (name !== "dc_session" || value === undefined) return undefined;
      return { name, value };
    },
  };
}
