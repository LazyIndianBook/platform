"use client";

// ⌘K / Ctrl K: one box to jump anywhere. The pages are the modules the manifest opens; Recent is what this tab
// opened lately (sessionStorage, never kept beyond the tab); Actions are the common starts (invite someone, record an
// incident, log a data request, the shortcuts, sign out); from two letters on, customers and staff are searched
// through the API's ?q= (as far as the person may). A combobox with its listbox (WAI-ARIA): the arrows move, Enter
// opens, Escape closes; the results' count is said politely.
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { useManifest } from "@/components/shell/manifest";
import { signOut } from "@/components/shell/sign-out";
import { Dialog, DialogContent, DialogDescription, DialogHeader } from "@/components/ui/dialog";
import { listPeople, listUsers } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, moduleHref, P, visibleModules } from "@/lib/modules";
import { ERP_URL } from "@/lib/site";

export type PaletteItem = { id: string; label: string; hint?: string; href?: string; run?: () => void };
type Group = { key: string; label: string; items: PaletteItem[] };

const RECENT_KEY = "examleaf-admin:recent";

export function readRecent(): PaletteItem[] {
  try {
    const items = JSON.parse(window.sessionStorage.getItem(RECENT_KEY) ?? "[]") as { href: string; label: string }[];
    return items.map((item) => ({ id: `recent:${item.href}`, label: item.label, href: item.href }));
  } catch {
    return [];
  }
}

/** Remembers a page this tab opened (at most 8, newest first). */
export function rememberRecent(href: string, label: string) {
  if (!label) return;
  try {
    const items = (JSON.parse(window.sessionStorage.getItem(RECENT_KEY) ?? "[]") as { href: string; label: string }[])
      .filter((item) => item.href !== href)
      .slice(0, 7);
    window.sessionStorage.setItem(RECENT_KEY, JSON.stringify([{ href, label }, ...items]));
  } catch {
    // storage off: no recent pages
  }
}

const matches = (query: string, ...texts: (string | undefined)[]) =>
  !query || texts.some((text) => text?.toLowerCase().includes(query.toLowerCase()));

export function CommandPalette({
  open,
  onOpenChange,
  onShortcuts,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onShortcuts: () => void;
}) {
  const id = useId();
  const router = useRouter();
  const manifest = useManifest();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [found, setFound] = useState<{ query: string; customers: PaletteItem[]; people: PaletteItem[] } | null>(null);
  const [state, setState] = useState<"idle" | "searching" | "failed">("idle");
  const q = query.trim();
  // read when it opens (closed on the server and at hydration, so no storage is read there)
  const recent = open ? readRecent() : [];

  useEffect(() => {
    if (q.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setState("searching");
      const [customers, people] = await Promise.allSettled([
        has(manifest, P.usersView) ? listUsers({ q }, undefined) : Promise.resolve(null),
        has(manifest, P.peopleView) ? listPeople({ q }, undefined) : Promise.resolve(null),
      ]);
      if (controller.signal.aborted) return;
      const failed = [customers, people].some((answer) => answer.status === "rejected");
      setState(failed ? "failed" : "idle");
      setFound({
        query: q,
        customers:
          customers.status === "fulfilled" && customers.value
            ? customers.value.results.slice(0, 6).map((user) => ({
                id: `user:${user.id}`,
                label: user.name || user.masked_email || user.id,
                hint: user.masked_email ?? undefined,
                href: `/users/${user.id}/`,
              }))
            : [],
        people:
          people.status === "fulfilled" && people.value
            ? people.value.results.slice(0, 6).map((person) => ({
                id: `person:${person.id}`,
                label: person.name || person.email,
                hint: person.email,
                href: `/people/${person.id}/`,
              }))
            : [],
      });
    }, 250);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [q, manifest]);

  const pages = visibleModules(manifest, ERP_URL)
    .map((module) => ({
      id: `page:${module.key}`,
      label: copy.nav.modules[module.key],
      hint: module.erp ? copy.shell.erp : undefined,
      href: moduleHref(module, ERP_URL),
    }))
    .concat({ id: "page:account", label: copy.nav.modules.account, hint: undefined, href: "/account/" });

  const actions: PaletteItem[] = [
    ...(has(manifest, P.peopleInvite)
      ? [{ id: "action:invite", label: copy.palette.inviteAction, href: "/people/#invite" }]
      : []),
    ...(has(manifest, P.incidentsAdd)
      ? [{ id: "action:incident", label: copy.palette.incidentAction, href: "/privacy/incidents/#new" }]
      : []),
    ...(has(manifest, P.requestsAdd)
      ? [{ id: "action:request", label: copy.palette.requestAction, href: "/privacy/requests/#new" }]
      : []),
    { id: "action:shortcuts", label: copy.palette.shortcutsAction, run: onShortcuts },
    { id: "action:sign-out", label: copy.palette.signOutAction, run: () => signOut() },
  ];

  const results = found && found.query === q && q.length >= 2 ? found : null;
  const groups: Group[] = [
    { key: "pages", label: copy.palette.pages, items: pages.filter((item) => matches(q, item.label, item.hint)) },
    { key: "recent", label: copy.palette.recent, items: q ? [] : recent },
    { key: "actions", label: copy.palette.actions, items: actions.filter((item) => matches(q, item.label)) },
    { key: "customers", label: copy.palette.customers, items: results?.customers ?? [] },
    { key: "people", label: copy.palette.people, items: results?.people ?? [] },
  ].filter((group) => group.items.length > 0);
  const flat = groups.flatMap((group) => group.items);
  const current = Math.min(active, Math.max(flat.length - 1, 0));
  const optionId = (index: number) => `${id}-option-${index}`;

  const close = () => {
    setQuery("");
    setActive(0);
    setFound(null);
    setState("idle");
    onOpenChange(false);
  };

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    close();
    if (item.run) return item.run();
    if (!item.href) return;
    if (/^https?:\/\//.test(item.href)) window.open(item.href, "_blank", "noopener,noreferrer");
    else router.push(item.href);
  };

  const status =
    state === "searching"
      ? copy.palette.searching
      : state === "failed"
        ? copy.palette.failed
        : flat.length
          ? ""
          : copy.palette.nothing;

  let index = -1;
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="w-[min(40rem,calc(100%-32px))] [&[open]]:mt-[10vh]">
        <DialogHeader>{copy.palette.title}</DialogHeader>
        <DialogDescription className="m-0 text-sm text-muted-foreground">{copy.palette.hint}</DialogDescription>
        <input
          role="combobox"
          aria-expanded={flat.length > 0}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={flat.length ? optionId(current) : undefined}
          aria-label={copy.palette.label}
          placeholder={copy.palette.placeholder}
          value={query}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              const step = event.key === "ArrowDown" ? 1 : -1;
              setActive((current + step + flat.length) % Math.max(flat.length, 1));
            } else if (event.key === "Enter") {
              event.preventDefault();
              choose(flat[current]);
            }
          }}
          className="min-h-12 w-full rounded-lg border-[1.5px] border-input bg-card px-3.5 text-base focus-visible:border-primary"
        />
        <div
          id={`${id}-list`}
          role="listbox"
          aria-label={copy.palette.title}
          className="flex max-h-[50vh] flex-col gap-3 overflow-y-auto"
        >
          {groups.map((group) => (
            <div key={group.key} role="group" aria-labelledby={`${id}-${group.key}`}>
              <div id={`${id}-${group.key}`} role="presentation" className="px-2 pb-1 label-mono text-[12px] uppercase">
                {group.label}
              </div>
              {group.items.map((item) => {
                index += 1;
                const mine = index;
                return (
                  <div
                    key={item.id}
                    id={optionId(mine)}
                    role="option"
                    aria-selected={mine === current}
                    onMouseMove={() => setActive(mine)}
                    onClick={() => choose(item)}
                    className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-[3px] px-2 text-[15px] aria-selected:bg-secondary aria-selected:shadow-[inset_3px_0_0_var(--primary)]"
                  >
                    <span className="min-w-0 truncate font-semibold">{item.label}</span>
                    {item.hint ? (
                      <span className="min-w-0 truncate text-sm text-muted-foreground">{item.hint}</span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p aria-live="polite" className="m-0 text-sm text-muted-foreground">
          {status}
        </p>
      </DialogContent>
    </Dialog>
  );
}
