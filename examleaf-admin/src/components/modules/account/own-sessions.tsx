"use client";

// The person's own sessions through the staff API (GET people/me/sessions/, every member of staff's; audited when one
// ends): each browser and system, where from (the address cut short), since when and last seen, this one marked; End
// one (POST …/{id}/end/), End every other session (POST …/end-others/, the app's refresh tokens too), and Sign out
// everywhere (this one too, last).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { signOutEverywhere } from "@/components/shell/sign-out";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { endOtherSessions, endOwnSession, type OwnSession } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

const words = copy.management.sessions;

export function OwnSessions({ sessions }: { sessions: OwnSession[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [ending, setEnding] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const others = sessions.filter((session) => !session.current).length;
  return (
    <div className="flex flex-col gap-4">
      <ErrorSummary error={error} />
      <ul className="m-0 flex list-none flex-col p-0">
        {[...sessions]
          .sort((a, b) => Number(b.current) - Number(a.current))
          .map((session) => {
            const name = words.device(session.browser, session.system);
            return (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border py-2.5 text-[15px]"
              >
                <span className="flex min-w-0 flex-col">
                  <span>
                    {name} ·{" "}
                    <span className="font-mono text-[14px]">{session.place || copy.account.addressUnknown}</span>
                    {session.current ? (
                      <>
                        {" "}
                        · <strong>{words.thisOne}</strong>
                      </>
                    ) : null}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {words.since(formatDateTime(session.created_at))} ·{" "}
                    {words.lastSeen(formatDateTime(session.last_seen_at))}
                  </span>
                </span>
                {session.current ? (
                  <span className="text-muted-foreground">{copy.account.now}</span>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    busy={busy && ending === session.id}
                    onClick={() => {
                      setEnding(session.id);
                      void run(async () => {
                        await endOwnSession(session.id);
                        toast.success(words.ended);
                        router.refresh();
                      });
                    }}
                  >
                    {words.end} <span className="sr-only">{words.endName(name)}</span>
                  </Button>
                )}
              </li>
            );
          })}
      </ul>
      <div className="flex flex-wrap gap-3">
        {others ? (
          <ConfirmDialog
            triggerLabel={words.endOthers}
            title={words.endOthers}
            text={words.endOthersText}
            confirmLabel={words.endOthers}
            onConfirm={() => endOtherSessions()}
            onDone={(result) => {
              toast.success(words.endedOthers((result as { sessions: number }).sessions));
              router.refresh();
            }}
          />
        ) : null}
        <Button
          variant="destructive"
          size="sm"
          busy={leaving}
          onClick={() => {
            setLeaving(true);
            // the sign-in page loads once it worked; the others still signed in: said above, the button back
            void run(signOutEverywhere).then((left) => left || setLeaving(false));
          }}
        >
          {copy.account.signOutEverywhere}
        </Button>
      </div>
      <p className="m-0 text-sm text-muted-foreground">{copy.account.signOutEverywhereText}</p>
    </div>
  );
}
