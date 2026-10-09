"use client";

// While the person is signed in to the website as a customer (the manifest's `impersonating`): a banner that says as
// whom and until when, and End. It cannot be dismissed; it sticks with the TEST band above the page (banners.tsx).
// It goes when the window ends.
import { useRouter } from "next/navigation";

import { useNow } from "@/components/data/clock";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { errorText } from "@/lib/api/errors";
import { endImpersonation, type Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";

export function ImpersonationBanner({
  impersonating,
  now: start,
}: {
  impersonating: NonNullable<Manifest["impersonating"]>;
  now: number;
}) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const now = useNow(start, 15_000);

  if (Date.parse(impersonating.until) <= now) return null;
  return (
    <section
      aria-label={copy.shell.impersonating(impersonating.email, formatTime(impersonating.until))}
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b-[1.5px] border-warning-line bg-warning-bg px-4 py-2 text-foreground nav:px-6"
    >
      <p className="m-0 text-[15px] font-semibold">
        {copy.shell.impersonating(impersonating.email, formatTime(impersonating.until))}
      </p>
      <div className="flex items-center gap-3">
        {error ? <p className="m-0 text-sm font-semibold text-destructive">{errorText(error)}</p> : null}
        <Button
          size="sm"
          variant="secondary"
          busy={busy}
          onClick={() =>
            run(async () => {
              await endImpersonation(impersonating.user_id);
              toast.success(copy.shell.impersonationEnded);
              router.refresh();
            })
          }
        >
          {copy.shell.endImpersonation}
        </Button>
      </div>
    </section>
  );
}
