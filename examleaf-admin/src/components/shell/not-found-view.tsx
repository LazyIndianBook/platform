// The 404 of the console: plainly, with the way home.
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/lib/copy";

export function NotFoundView() {
  return (
    <div className="flex max-w-[44rem] flex-col gap-4 py-6 [&>*]:m-0">
      <p aria-hidden="true" className="font-mono text-2xl font-semibold text-red-ink">
        [ ? ]
      </p>
      <h1 className="text-[clamp(26px,3.4vw,34px)] leading-tight">{copy.errors.notFoundTitle}</h1>
      <p className="text-[17px] leading-relaxed text-ink/85">{copy.errors.notFoundText}</p>
      <p>
        <Link href="/" className={buttonVariants({ variant: "primary" })}>
          {copy.errors.goHome}
        </Link>
      </p>
    </div>
  );
}
