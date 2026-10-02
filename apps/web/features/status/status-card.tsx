import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ApiResult, HealthResponse } from "@/lib/api/client";

import { statusView } from "./status-view";

type StatusCardProps = {
  health: ApiResult<HealthResponse>;
  ready: ApiResult<HealthResponse>;
};

export function StatusCard({ health, ready }: StatusCardProps) {
  const view = statusView(health, ready);

  return (
    <Card>
      <CardHeader>
        <CardTitle>API and database</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {view.state === "ok" ? (
          <p>
            <Badge>OK</Badge> <span>API and database are ready.</span>
          </p>
        ) : null}
        {view.state === "database_not_ready" ? (
          <ErrorDetails
            label="Database is not ready."
            code={view.code}
            requestId={view.requestId}
          />
        ) : null}
        {view.state === "unreachable" ? <p>API unreachable.</p> : null}
        {view.state === "error" ? (
          <ErrorDetails label="The API returned an error." code={view.code} requestId={view.requestId} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function ErrorDetails({
  label,
  code,
  requestId,
}: {
  label: string;
  code: string;
  requestId: string;
}) {
  return (
    <div>
      <p>{label}</p>
      <p>
        Code: <span>{code}</span>
      </p>
      {requestId === "" ? null : (
        <p>
          Request ID: <span>{requestId}</span>
        </p>
      )}
    </div>
  );
}
