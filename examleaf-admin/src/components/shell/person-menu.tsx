"use client";

// The person's menu in the top bar: who is signed in and with which roles (and until when), their account and
// sessions, the keyboard shortcuts (and the switch for single-key ones, WCAG 2.1.4), Sign out and Sign out everywhere.
import { ChevronDown, UserRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useManifest } from "@/components/shell/manifest";
import { Popover } from "@/components/shell/popover";
import { signOut, signOutEverywhere } from "@/components/shell/sign-out";
import { rolesOf } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate } from "@/lib/format";
import { setShortcutsEnabled, useShortcutsEnabled } from "@/lib/shortcuts";

const item =
  "flex min-h-11 w-full cursor-pointer items-center rounded-[3px] px-2.5 text-left text-[15px] font-semibold text-foreground no-underline hover:bg-secondary hover:text-foreground hover:no-underline";

export function PersonMenu({ onShortcuts }: { onShortcuts: () => void }) {
  const manifest = useManifest();
  const shortcuts = useShortcutsEnabled();
  const [leaving, setLeaving] = useState(false);
  const name = manifest.user.full_name || manifest.user.email;
  const roles = rolesOf(manifest);

  return (
    <Popover
      buttonClassName="min-w-11 justify-center gap-1.5 border-transparent px-2 hover:bg-secondary"
      button={
        <>
          <span
            aria-hidden="true"
            className="inline-flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground"
          >
            <UserRound className="size-[18px]" />
          </span>
          {/* the name names the button (visible from 1100 px), then what it opens */}
          <span className="max-w-40 truncate max-[1099px]:sr-only">{name}</span>
          <span className="sr-only">{copy.shell.yourAccount}</span>
          <ChevronDown aria-hidden="true" className="size-4 max-[399px]:hidden" />
        </>
      }
      panelClassName="w-72"
    >
      {(close) => (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-0.5 border-b border-border px-2.5 pb-2.5">
            <p className="m-0 font-semibold break-words">{name}</p>
            <p className="m-0 text-sm break-all text-muted-foreground">{manifest.user.email}</p>
            {roles.length ? (
              <p className="m-0 mt-1 text-sm">
                <span className="text-muted-foreground">{copy.shell.roles}: </span>
                {roles
                  .map((role) =>
                    role.expires_at
                      ? `${labelOf(copy.people.roleNames, role.name)} (${copy.account.roleUntil(formatDate(role.expires_at))})`
                      : labelOf(copy.people.roleNames, role.name),
                  )
                  .join(", ")}
              </p>
            ) : null}
          </div>
          <Link href="/account/" className={item} onClick={close}>
            {copy.shell.account}
          </Link>
          <button
            type="button"
            className={item}
            onClick={() => {
              close();
              onShortcuts();
            }}
          >
            {copy.shell.shortcuts}
          </button>
          <label className={`${item} justify-between gap-3 font-normal`}>
            <span>{copy.shell.shortcutsSwitch}</span>
            <input
              type="checkbox"
              role="switch"
              data-slot="switch"
              checked={shortcuts}
              onChange={(event) => setShortcutsEnabled(event.target.checked)}
            />
          </label>
          <div className="flex flex-col border-t border-border pt-2">
            <button
              type="button"
              className={item}
              aria-busy={leaving || undefined}
              onClick={() => {
                setLeaving(true);
                signOut();
              }}
            >
              {copy.common.signOut}
            </button>
            <button
              type="button"
              className={item}
              onClick={() => {
                setLeaving(true);
                signOutEverywhere();
              }}
            >
              {copy.shell.signOutEverywhere}
            </button>
          </div>
        </div>
      )}
    </Popover>
  );
}
