"use client";

type AppErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function AppError({ reset }: AppErrorProps) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="mt-2">The page could not be shown.</p>
      <button type="button" className="mt-4 underline" onClick={reset}>
        Try again
      </button>
    </section>
  );
}
