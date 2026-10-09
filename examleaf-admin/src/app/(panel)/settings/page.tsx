// /settings/: the site's switches and the feature flags (GET settings/ and flags/), each with its source, history and
// the change with a reason and an optional effective date for whoever may (components/modules/settings/).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { SettingsList } from "@/components/modules/settings/settings-list";
import { PageHeader, Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { type Flag, listFlags, listSettings, type Setting } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.settings.title };

function Part({ kind, answer }: { kind: "settings" | "flags"; answer: (Setting | Flag)[] | ApiError }) {
  if (answer instanceof ApiError) return <Problem error={answer} />;
  if (!answer.length)
    return (
      <EmptyState title={copy.settings.emptyTitle}>
        <p>{copy.settings.emptyText}</p>
      </EmptyState>
    );
  return <SettingsList kind={kind} rows={answer} />;
}

export default async function SettingsPage() {
  const { manifest, transport, path } = await staffPage("/settings/");
  const [settings, flags] = await Promise.all([
    has(manifest, P.settingsView) ? attempt(listSettings(transport), path) : null,
    has(manifest, P.flagsView) ? attempt(listFlags(transport), path) : null,
  ]);
  return (
    <>
      <PageHeader
        title={copy.settings.title}
        lead={copy.settings.lead}
        actions={
          has(manifest, P.apiKeysView) ? (
            <Link href="/settings/api-keys/" className="inline-flex min-h-11 items-center font-semibold">
              {copy.nav.modules.apiKeys}
            </Link>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {settings ? (
          <Section id="site" title={copy.settings.site}>
            <Part kind="settings" answer={settings} />
          </Section>
        ) : null}
        {flags ? (
          <Section id="flags" title={copy.settings.flags}>
            <Part kind="flags" answer={flags} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
