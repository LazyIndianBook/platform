// The honest states of the personal shop pages: the API cannot answer (Unavailable), it refuses with a reason (403:
// the email address not confirmed yet, the shop not open, a parent's consent awaited), or an account is needed.
import Link from "next/link";

import { Unavailable } from "@/components/site/unavailable";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import type { ApiError } from "@/lib/api/errors";
import { withNext } from "@/lib/auth/next-url";

export function ShopProblem({ error, retry, what }: { error: ApiError; retry: string; what: string }) {
  if (error.unavailable) return <Unavailable what={what} retry={retry} />;
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site">
        <EmptyState
          art="cart"
          title={error.message}
          action={
            <Link href="/account/" className={buttonVariants({ variant: "primary" })}>
              My account
            </Link>
          }
          after={
            <Link href="/contact/" className="inline-flex min-h-11 items-center font-semibold">
              Contact us
            </Link>
          }
        >
          <p>{what} needs this first. My account shows what is still to do.</p>
        </EmptyState>
      </div>
    </section>
  );
}

/** A course opens in an account, so a visitor's cart with one checks out signed in (the API refuses a guest's). */
export function SignInToBuy({ next }: { next: string }) {
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site">
        <EmptyState
          art="cart"
          title="Log in or register for the course"
          action={
            <Link href={withNext("/account/login/", next)} className={buttonVariants({ variant: "primary" })}>
              Log in
            </Link>
          }
          after={
            <Link href={withNext("/account/signup/", next)} className="inline-flex min-h-11 items-center font-semibold">
              Register free
            </Link>
          }
        >
          <p>
            The revision course opens in your ExamLeaf account. Log in, or register free, and you come back here: your
            cart comes with you.
          </p>
        </EmptyState>
      </div>
    </section>
  );
}
