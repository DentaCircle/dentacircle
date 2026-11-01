export default function Loading() {
  return (
    <div role="status" aria-label="Loading workspace" className="space-y-6">
      <span className="sr-only">Loading your clinic workspace…</span>
      <div aria-hidden="true" className="space-y-6 motion-safe:animate-pulse">
        <div className="h-9 w-48 rounded-lg bg-muted" />
        <div className="h-60 rounded-xl bg-muted" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0, 1, 2, 3].map((key) => <div key={key} className="h-40 rounded-xl border bg-card" />)}</div>
      </div>
    </div>
  );
}
