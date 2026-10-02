import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { ApiResult, HealthResponse } from "@/lib/api/client";
import { StatusCard } from "@/features/status/status-card";

const marker = "synthetic-marker-raw-body";
const ok: ApiResult<HealthResponse> = { ok: true, data: { status: "ok" } };

test("shows ready when the API and database answer ok", () => {
  render(<StatusCard health={ok} ready={ok} />);

  expect(screen.getByText("API and database are ready.")).toBeInTheDocument();
});

test("shows the database error code and request id, not the raw body", () => {
  render(
    <StatusCard
      health={ok}
      ready={{
        ok: false,
        error: {
          kind: "api",
          status: 503,
          code: "service_unavailable",
          message: marker,
          requestId: "req-9",
        },
      }}
    />,
  );

  expect(screen.getByText("Database is not ready.")).toBeInTheDocument();
  expect(screen.getByText("service_unavailable")).toBeInTheDocument();
  expect(screen.getByText("req-9")).toBeInTheDocument();
  expect(screen.queryByText(marker)).not.toBeInTheDocument();
});

test("shows API unreachable when the API cannot be contacted", () => {
  render(
    <StatusCard
      health={{ ok: false, error: { kind: "network", message: marker } }}
      ready={ok}
    />,
  );

  expect(screen.getByText("API unreachable.")).toBeInTheDocument();
  expect(screen.queryByText(marker)).not.toBeInTheDocument();
});
