"use client";

// "We're confirming your payment" (States, "Payment pending"): the done page asks the server once more after a few
// seconds (router.refresh(): the page is drawn again from the API's answer), and only once. Confirmed, the done page
// replaces this box; still pending, the box says where the result will be. It never claims the payment itself.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

const WAIT = 10_000;

export function Confirming({ number, href }: { number: string; href: string }) {
  const router = useRouter();
  const [asked, setAsked] = useState(false);
  const [asking, startAsking] = useTransition();
  useEffect(() => {
    const timer = setTimeout(() => {
      setAsked(true);
      startAsking(() => router.refresh());
    }, WAIT);
    return () => clearTimeout(timer);
  }, [router]);
  const answered = asked && !asking; // and still pending: a confirmed order's page no longer draws this box
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-[4px] border border-border bg-card px-3.5 py-3 text-[15px] leading-normal"
    >
      {answered ? (
        <span>
          Not confirmed yet. <Link href={href}>The order&apos;s page</Link> shows the result, and we email you either
          way.
        </span>
      ) : (
        <>
          <span
            aria-hidden="true"
            className="size-4 shrink-0 rounded-full border-2 border-border border-t-primary motion-safe:animate-[el-spin_0.8s_linear_infinite]"
          />
          <span>Checking {number}. This page updates once.</span>
        </>
      )}
    </div>
  );
}
