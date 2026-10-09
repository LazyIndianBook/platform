// /privacy/disclosures/: the e-commerce disclosures and the privacy contacts (GET privacy/disclosures/: the site
// settings of the group "disclosures"), one form saved with one reason for whoever may change settings, read-only for
// the others; and the group's history, newest first.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { DisclosuresForm, DisclosuresView } from "@/components/modules/privacy/disclosures";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getDisclosures } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.legal.disclosuresTitle };

const shown = (value: unknown) => (value === null || value === undefined || value === "" ? "" : String(value));

export default async function DisclosuresPage() {
  const { manifest, transport, path } = await staffPage("/privacy/disclosures/");
  const disclosures = await attempt(getDisclosures(transport), path);
  const header = <PageHeader title={copy.legal.disclosuresTitle} lead={copy.legal.disclosuresLead} />;
  if (disclosures instanceof ApiError)
    return (
      <>
        {header}
        <Problem error={disclosures} />
      </>
    );
  const labels = Object.fromEntries(disclosures.settings.map((setting) => [setting.key, setting.label]));
  // the settings of a few choices (their words in the copy); the others are free text, shown as they are
  const choices = new Set(disclosures.settings.filter((setting) => Array.isArray(setting.kind)).map((row) => row.key));
  const me = manifest.user.id;
  return (
    <>
      {header}
      <div className="flex flex-col gap-10">
        <Section id="form" title={copy.legal.disclosuresForm}>
          {has(manifest, P.settingsManage) ? (
            <DisclosuresForm settings={disclosures.settings} />
          ) : (
            <DisclosuresView settings={disclosures.settings} />
          )}
        </Section>
        <Section id="history" title={copy.legal.history} lead={copy.legal.historyLead}>
          {disclosures.history.length ? (
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {disclosures.history.map((row, index) => (
                <li
                  key={`${row.key}-${row.created}-${index}`}
                  className="flex flex-col gap-0.5 border-t border-border pt-3"
                >
                  <span className="text-sm font-semibold">{labels[row.key] ?? row.key}</span>
                  <span className="text-[15px] break-words whitespace-pre-wrap">
                    {!shown(row.value)
                      ? copy.legal.emptyValue
                      : choices.has(row.key)
                        ? labelOf(copy.legal.choices, shown(row.value))
                        : shown(row.value)}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {copy.legal.historyLine(staffLabel(row.changed_by, me), formatDateTime(row.created))}
                    {row.reason ? ` · “${row.reason}”` : ""}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.noHistory}</p>
          )}
        </Section>
      </div>
    </>
  );
}
