// The honest state when Django cannot be reached (or answers with an error): what happened and one way forward.
// Never stale or made-up data in its place.
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export function Unavailable({ retry = "/", what = "This page" }: { retry?: string; what?: string }) {
  return (
    <section className="section">
      <div className="container-site">
        <EmptyState
          art="missing"
          title="ExamLeaf cannot be reached just now"
          action={
            <Link href={retry} className={buttonVariants({ variant: "primary" })}>
              Try again
            </Link>
          }
        >
          <p>{what} needs our server, which is not answering. Please try again in a minute.</p>
        </EmptyState>
      </div>
    </section>
  );
}
