"use client";

// While the person is signed in to the website as a customer (the manifest's `impersonating`: the masked address and
// until when): a banner that says so, and End, which needs the token this tab was given when it started
// (POST users/{id}/impersonate/end/ with it). Another tab, or a reload after the tab lost it, has no token: the
// banner says when it ends instead (the website's own banner can end it too). It cannot be dismissed; it sticks with
// the TEST band above the page (banners.tsx). It goes when the window ends.
import { useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";

import { useNow } from "@/components/data/clock";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { errorText } from "@/lib/api/errors";
import { endImpersonation, impersonationToken, type Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatTime } from "@/lib/format";

const never = () => () => undefined;

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
  const token = useSyncExternalStore(
    never,
    () => impersonationToken(impersonating.user_id),
    () => null,
  );

  if (Date.parse(impersonating.until) <= now) return null;
  const words = copy.shell.impersonating(impersonating.email, formatTime(impersonating.until));
  return (
    <section
      aria-label={words}
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b-[1.5px] border-warning-line bg-warning-bg px-4 py-2 text-foreground nav:px-6"
    >
      <p className="m-0 text-[15px] font-semibold">
        {words}
        {token ? null : <span className="font-normal"> {copy.shell.impersonationElsewhere}</span>}
      </p>
      {token ? (
        <div className="flex items-center gap-3">
          {error ? <p className="m-0 text-sm font-semibold text-destructive">{errorText(error)}</p> : null}
          <Button
            size="sm"
            variant="secondary"
            busy={busy}
            onClick={() =>
              run(async () => {
                await endImpersonation(impersonating.user_id, token);
                toast.success(copy.shell.impersonationEnded);
                router.refresh();
              })
            }
          >
            {copy.shell.endImpersonation}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
