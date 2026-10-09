"use client";

// The console's frame around every signed-in page: the TEST and impersonation banners when they hold, the top bar (the
// Menu button under 900 px, Search with ⌘K, the inbox and its count, the person's menu), the sidebar of modules, and
// the page. Mounted once for the panel: the command palette, the shortcuts list, "confirm it's you" and the idle
// watcher. ⌘K / Ctrl K opens the palette anywhere; "?" lists the shortcuts while single-key shortcuts are on.
import { Inbox as InboxIcon, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Banners } from "@/components/shell/banners";
import { Brand } from "@/components/shell/brand";
import { CommandPalette, rememberRecent } from "@/components/shell/command-palette";
import { IdleWatcher } from "@/components/shell/idle-watcher";
import { useManifest } from "@/components/shell/manifest";
import { PersonMenu } from "@/components/shell/person-menu";
import { ReauthDialog } from "@/components/shell/reauth-dialog";
import { SessionGate } from "@/components/shell/session-gate";
import { ShortcutsDialog } from "@/components/shell/shortcuts-dialog";
import { Sidebar } from "@/components/shell/sidebar";
import type { InboxCount } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";
import { notForShortcuts, useShortcutsEnabled } from "@/lib/shortcuts";

export function Shell({ inbox, now, children }: { inbox: InboxCount | null; now: number; children: React.ReactNode }) {
  const manifest = useManifest();
  const pathname = usePathname();
  const search = useSearchParams();
  const shortcuts = useShortcutsEnabled();
  const [palette, setPalette] = useState(false);
  const [keys, setKeys] = useState(false);
  const [menuOn, setMenuOn] = useState<string | null>(null);
  const menuOpen = menuOn === pathname; // a new page closes it
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette(true);
        return;
      }
      if (event.key === "Escape" && menuOn) {
        setMenuOn(null);
        menuButton.current?.focus();
        return;
      }
      if (shortcuts && event.key === "?" && !notForShortcuts(event)) {
        event.preventDefault();
        setKeys(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcuts, menuOn]);

  // what this tab opened, for the palette's Recent: the page's own heading once it has rendered
  const query = search.toString();
  useEffect(() => {
    const timer = setTimeout(() => {
      const heading = document.querySelector("main h1")?.textContent?.trim() ?? "";
      rememberRecent(query ? `${pathname}?${query}` : pathname, heading);
    }, 300);
    return () => clearTimeout(timer);
  }, [pathname, query]);

  return (
    <>
      <a className="skip-link" href="#main">
        {copy.app.skip}
      </a>
      <Banners manifest={manifest} now={now} />
      <div className="console">
        <header className="console-top">
          <button
            ref={menuButton}
            type="button"
            aria-expanded={menuOpen}
            aria-controls="console-side"
            onClick={() => setMenuOn(menuOpen ? null : pathname)}
            className="inline-flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-btn border-[1.5px] border-foreground px-2.5 text-[15px] font-bold nav:hidden"
          >
            {menuOpen ? <X aria-hidden="true" className="size-5" /> : <Menu aria-hidden="true" className="size-5" />}
            <span className="max-[399px]:sr-only">{menuOpen ? copy.shell.closeMenu : copy.shell.menu}</span>
          </button>
          <Brand className="max-[399px]:hidden nav:hidden" wordmarkClassName="max-[479px]:sr-only" />
          <button
            type="button"
            onClick={() => setPalette(true)}
            aria-keyshortcuts="Meta+K Control+K"
            className="inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-2.5 rounded-lg border-[1.5px] border-input bg-card px-2.5 text-[15px] text-muted-foreground hover:border-foreground max-nav:ml-auto nav:w-[min(26rem,40vw)] nav:justify-start nav:px-3"
          >
            <Search aria-hidden="true" className="size-5 shrink-0" />
            <span className="max-nav:sr-only">{copy.shell.search}</span>
            <kbd className="ml-auto max-nav:hidden">⌘K</kbd>
          </button>
          <div className="flex items-center gap-1 nav:ml-auto">
            {has(manifest, P.inboxView) ? (
              <Link
                href="/inbox/"
                className="inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-btn px-2 text-[15px] font-semibold text-foreground no-underline hover:bg-secondary hover:no-underline"
              >
                {/* its name is what it shows, "Inbox 6", then "open" for screen readers (WCAG 2.5.3) */}
                <InboxIcon aria-hidden="true" className="size-5 shrink-0 min-[1100px]:hidden" />
                <span className="max-[1099px]:sr-only">{copy.shell.inbox}</span>
                {inbox && inbox.open > 0 ? (
                  <>
                    {" "}
                    <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-primary px-1.5 font-mono text-xs font-semibold text-primary-foreground">
                      {inbox.open}
                    </span>{" "}
                    <span className="sr-only">{copy.shell.inboxOpen}</span>
                  </>
                ) : null}
              </Link>
            ) : null}
            <PersonMenu onShortcuts={() => setKeys(true)} />
          </div>
        </header>
        <aside id="console-side" className="console-side" data-open={menuOpen || undefined}>
          <div className="px-6 pt-4 max-nav:hidden">
            <Brand />
          </div>
          <Sidebar onNavigate={() => setMenuOn(null)} />
        </aside>
        <main id="main" tabIndex={-1} className="console-main">
          {children}
        </main>
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} onShortcuts={() => setKeys(true)} />
      <ShortcutsDialog open={keys} onOpenChange={setKeys} />
      <ReauthDialog />
      <SessionGate />
      <IdleWatcher idleSeconds={manifest.idle_timeout_s} absoluteEnd={manifest.absolute_expires_at} />
    </>
  );
}
