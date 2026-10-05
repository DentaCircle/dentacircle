import Link from "next/link";

export default function NotFound() {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2">
        <Link href="/" className="underline">
          Back to dashboard
        </Link>
      </p>
    </section>
  );
}
