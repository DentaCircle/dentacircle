import { afterEach, describe, expect, test } from "vitest";

import nextConfig, { apiProxyBaseUrl } from "@/next.config";

afterEach(() => {
  delete process.env.API_BASE_URL;
});

describe("api rewrite", () => {
  test("proxies /api to the default API origin", async () => {
    delete process.env.API_BASE_URL;

    await expect(rewrites()).resolves.toEqual([
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/:path*" },
    ]);
  });

  test("uses API_BASE_URL and drops a trailing slash", async () => {
    process.env.API_BASE_URL = "http://api.test:9000/";

    expect(apiProxyBaseUrl()).toBe("http://api.test:9000");
    await expect(rewrites()).resolves.toEqual([
      { source: "/api/:path*", destination: "http://api.test:9000/:path*" },
    ]);
  });
});

function rewrites(): ReturnType<NonNullable<typeof nextConfig.rewrites>> {
  if (nextConfig.rewrites === undefined) throw new Error("rewrites is missing");
  return nextConfig.rewrites();
}

test("does not log patient page or proxy paths containing identifiers", () => {
  const logging = nextConfig.logging;
  expect(logging && logging.incomingRequests).toEqual({
    ignore: [expect.any(RegExp)],
  });
  if (!logging || !logging.incomingRequests || typeof logging.incomingRequests === "boolean") {
    throw new Error("incoming request log filter is missing");
  }
  const ignored = logging.incomingRequests.ignore ?? [];
  expect(ignored.some((pattern) => pattern.test("/patients/example/messages"))).toBe(true);
  expect(ignored.some((pattern) => pattern.test("/api/patients/example/messages"))).toBe(true);
});
