import Link from "next/link";

import { BookScreen, type BookChoice } from "@/features/appointments/book-screen";
import { followUpsHref } from "@/features/follow-ups/links";

export type FollowUpBookPageProps =
  | { status: "forbidden" | "error" | "closed" | "no-clinicians" | "no-types" }
  | {
      status: "ready";
      followUpId: string;
      types: BookChoice[];
      clinicians: BookChoice[];
      today: string;
    };

export function FollowUpBookPage(props: FollowUpBookPageProps) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Book visit</h1>
        <Link href={followUpsHref("all", 1)}>Follow-ups</Link>
      </div>
      {props.status === "forbidden" ? <p role="alert">You do not have access.</p> : null}
      {props.status === "closed" ? <p role="alert">This follow-up is no longer open.</p> : null}
      {props.status === "no-clinicians" ? <p>No clinicians are set up.</p> : null}
      {props.status === "no-types" ? <p>No appointment types are set up.</p> : null}
      {props.status === "error" ? <p role="alert">Something went wrong.</p> : null}
      {props.status === "ready" ? (
        <BookScreen
          types={props.types}
          clinicians={props.clinicians}
          today={props.today}
          submitUrl={`/api/follow-ups/${props.followUpId}/book`}
          doneUrl={followUpsHref("all", 1, "booked")}
        />
      ) : null}
    </section>
  );
}
