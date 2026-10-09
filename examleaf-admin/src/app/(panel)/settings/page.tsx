// /settings/: the site's switches and the feature flags (GET settings/ and flags/), in the sections the API names for
// each (its `group`: the shop, consent, the course, maintenance, the disclosures …, the ERPNext sync's switches with
// their environment's value, the other flags), each with its source, history and the change with a reason and an
// optional effective date for whoever may (components/modules/settings/). A section the API adds later is drawn by
// its name; the connections, the message templates and the API keys are pages of their own.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { SettingsList } from "@/components/modules/settings/settings-list";
import { PageHeader, Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { type Flag, listFlags, listSettings, type Setting } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.settings.title };

const GROUP_ORDER = ["shop", "consent", "course", "maintenance", "site", "disclosures", "erp", "flags"];

/** Rows by their `group`, in the page's order (an unknown group after the known ones, by name). */
function grouped<T extends { group: string }>(rows: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const row of rows) groups.set(row.group || "site", [...(groups.get(row.group || "site") ?? []), row]);
  const rank = (group: string) => (GROUP_ORDER.includes(group) ? GROUP_ORDER.indexOf(group) : GROUP_ORDER.length);
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b));
}

function Part({ kind, answer }: { kind: "settings" | "flags"; answer: (Setting | Flag)[] | ApiError }) {
  if (answer instanceof ApiError) return <Problem error={answer} />;
  if (!answer.length)
    return (
      <EmptyState title={copy.settings.emptyTitle}>
        <p>{copy.settings.emptyText}</p>
      </EmptyState>
    );
  return (
    <div className="flex flex-col gap-10">
      {grouped(answer).map(([group, rows]) => (
        <Section
          key={`${kind}-${group}`}
          id={`${kind}-${group}`}
          title={labelOf(copy.management.settings.groups, group)}
          lead={copy.management.settings.groupsLead[group]}
        >
          <SettingsList kind={kind} rows={rows} />
        </Section>
      ))}
    </div>
  );
}

export default async function SettingsPage() {
  const { manifest, transport, path } = await staffPage("/settings/");
  const [settings, flags] = await Promise.all([
    has(manifest, P.settingsView) ? attempt(listSettings(transport), path) : null,
    has(manifest, P.flagsView) ? attempt(listFlags(transport), path) : null,
  ]);
  const links = [
    has(manifest, P.connectionsView) ? { href: "/settings/connections/", label: copy.nav.modules.connections } : null,
    has(manifest, P.templatesView) ? { href: "/settings/templates/", label: copy.nav.modules.templates } : null,
    has(manifest, P.apiKeysView) ? { href: "/settings/api-keys/", label: copy.nav.modules.apiKeys } : null,
  ].filter((link) => link !== null);
  return (
    <>
      <PageHeader
        title={copy.settings.title}
        lead={copy.settings.lead}
        actions={
          links.length ? (
            <nav aria-label={copy.management.settings.links} className="flex flex-wrap gap-x-5">
              {links.map((link) => (
                <Link key={link.href} href={link.href} className="inline-flex min-h-11 items-center font-semibold">
                  {link.label}
                </Link>
              ))}
            </nav>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {settings ? <Part kind="settings" answer={settings} /> : null}
        {flags ? <Part kind="flags" answer={flags} /> : null}
      </div>
    </>
  );
}
