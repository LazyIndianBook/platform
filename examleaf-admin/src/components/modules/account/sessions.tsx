"use client";

// The person's own signed-in devices (allauth.usersessions, GET/DELETE /_allauth/browser/v1/auth/sessions), as the
// public site's Log-in and security draws them: each browser, this one marked; another one signed out at once; and
// Sign out everywhere, which ends them all and this one last.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { signOutEverywhere } from "@/components/shell/sign-out";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { auth, type Session } from "@/lib/auth/headless";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

/** "Chrome on Android" from a browser's user agent: enough to recognise a device, never the whole string. */
export function deviceName(userAgent: string): string {
  const browser =
    [
      [/Edg\//, "Edge"],
      [/OPR\/|Opera/, "Opera"],
      [/SamsungBrowser/, "Samsung Internet"],
      [/Firefox\/|FxiOS/, "Firefox"],
      [/Chrome\/|CriOS/, "Chrome"],
      [/Safari\//, "Safari"],
    ].find(([pattern]) => (pattern as RegExp).test(userAgent))?.[1] ?? copy.account.aBrowser;
  const system =
    [
      [/Android/, "Android"],
      [/iPhone|iPad|iPod/, "iOS"],
      [/Windows/, "Windows"],
      [/Mac OS X|Macintosh/, "macOS"],
      [/CrOS/, "ChromeOS"],
      [/Linux/, "Linux"],
    ].find(([pattern]) => (pattern as RegExp).test(userAgent))?.[1] ?? null;
  return system ? copy.account.on(String(browser), String(system)) : String(browser);
}

/** An address shortened: 203.0.113.x, or an IPv6 address's first four groups. */
export function shortAddress(ip: string | null): string {
  if (!ip) return copy.account.addressUnknown;
  if (ip.includes(":")) return `${ip.split(":").slice(0, 4).join(":")}:…`;
  return ip.replace(/\.\d+$/, ".x");
}

export function Sessions({ sessions }: { sessions: Session[] }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [ending, setEnding] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <ErrorSummary error={error} />
      <ul className="m-0 flex list-none flex-col p-0">
        {[...sessions]
          .sort((a, b) => Number(b.is_current) - Number(a.is_current))
          .map((session) => {
            const name = deviceName(session.user_agent);
            return (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border py-2.5 text-[15px]"
              >
                <span className="flex min-w-0 flex-col">
                  <span>
                    {name} · <span className="font-mono text-[14px]">{shortAddress(session.ip)}</span>
                    {session.is_current ? (
                      <>
                        {" "}
                        · <strong>{copy.account.thisDevice}</strong>
                      </>
                    ) : null}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {copy.account.since(formatDateTime(session.created_at * 1000))}
                    {session.last_seen_at
                      ? ` · ${copy.account.lastSeen(formatDateTime(session.last_seen_at * 1000))}`
                      : ""}
                  </span>
                </span>
                {session.is_current ? (
                  <span className="text-muted-foreground">{copy.account.now}</span>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    busy={busy && ending === session.id}
                    onClick={() => {
                      setEnding(session.id);
                      run(async () => {
                        await auth.endSessions([session.id]);
                        toast.success(copy.account.signedOutDevice);
                        router.refresh();
                      });
                    }}
                  >
                    {copy.account.signOutDevice} <span className="sr-only">{name}</span>
                  </Button>
                )}
              </li>
            );
          })}
      </ul>
      <div className="flex flex-col gap-2">
        <p className="m-0 text-[15px] text-muted-foreground">{copy.account.signOutEverywhereText}</p>
        <div>
          <Button
            variant="destructive"
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
      </div>
    </div>
  );
}
