// /privacy/dark-pattern-audit/: the yearly self-audit (GET privacy/dark-pattern-audits/) for the year the cockpit says
// is due (GET privacy/cockpit/'s dark_pattern), or the year asked for (?year=): started, answered pattern by pattern,
// completed once with the year typed; afterwards as it was signed, with its certificate, the day the website shows it
// from and the signed copy. Whoever may keep the compliance duties edits; the others read.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { AuditForm, CertificateUpload, CompleteAudit, StartAudit } from "@/components/modules/privacy/dark-patterns";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { certificateHref, type DarkPatternAudit, getCockpit, listDarkPatternAudits } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.legal.darkTitle };

function Rows({ audit }: { audit: DarkPatternAudit }) {
  return (
    <ol className="m-0 flex list-none flex-col gap-4 p-0">
      {(audit.rows ?? []).map((row, index) => (
        <li key={row.pattern} className="flex flex-col gap-1 border-t border-border pt-3 text-[15px]">
          <h3 className="m-0 font-head text-lg">
            <span className="font-mono text-sm text-muted-foreground">{index + 1}. </span>
            {row.label}
          </h3>
          <p className="m-0">
            <span className="text-sm font-semibold text-muted-foreground">{copy.legal.finding}: </span>
            <span className="whitespace-pre-wrap">{row.finding || copy.common.none}</span>
          </p>
          <p className="m-0">
            <span className="text-sm font-semibold text-muted-foreground">{copy.legal.fix}: </span>
            <span className="whitespace-pre-wrap">{row.fix || copy.common.none}</span>
          </p>
        </li>
      ))}
    </ol>
  );
}

export default async function DarkPatternAuditPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/privacy/dark-pattern-audit/", params));
  const [audits, cockpit] = await Promise.all([
    attempt(listDarkPatternAudits(transport), path),
    has(manifest, P.requestsView) ? attempt(getCockpit(transport), path) : null,
  ]);
  const header = <PageHeader title={copy.legal.darkTitle} lead={copy.legal.darkLead} />;
  if (audits instanceof ApiError)
    return (
      <>
        {header}
        <Problem error={audits} />
      </>
    );
  const due = cockpit && !(cockpit instanceof ApiError) ? cockpit.dark_pattern : null;
  const asked = /^\d{4}$/.test(param(params, "year")) ? Number(param(params, "year")) : null;
  const year = asked ?? due?.year ?? audits.results[0]?.year ?? null;
  const audit = audits.results.find((row) => row.year === year) ?? null;
  const years = [...new Set([...(due ? [due.year] : []), ...audits.results.map((row) => row.year)])].sort(
    (a, b) => b - a,
  );
  const managing = has(manifest, P.complianceManage);
  const me = manifest.user.id;
  const state = audit ? (audit.completed_at ? "completed" : "draft") : "missing";

  return (
    <>
      {header}
      <div className="flex flex-col gap-10">
        {years.length > 1 ? (
          <nav aria-label={copy.legal.darkYears} className="-mt-3 overflow-x-auto border-b border-border">
            <ul className="m-0 flex list-none p-0">
              {years.map((each) => (
                <li key={each}>
                  <Link
                    href={`/privacy/dark-pattern-audit/?year=${each}`}
                    aria-current={each === year ? "page" : undefined}
                    className={`inline-flex min-h-11 items-center px-4 font-mono text-[15px] font-semibold no-underline ${
                      each === year
                        ? "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {each}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}

        {year === null ? (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.darkNoAudits}</p>
        ) : (
          <Section
            id="audit"
            title={copy.legal.darkYear(year)}
            actions={
              <StatusChip tone={state === "completed" ? "done" : state === "draft" ? "moving" : "waiting"}>
                {labelOf(copy.legal.darkStates, state)}
              </StatusChip>
            }
          >
            {due && due.year === year && state !== "completed" ? (
              <p className="m-0 text-[15px]">{copy.legal.darkDue(year, formatDate(due.due))}</p>
            ) : null}
            {!audit ? (
              managing && due?.year === year ? (
                <StartAudit year={year} />
              ) : (
                <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.darkMissingText}</p>
              )
            ) : audit.completed_at ? (
              <div className="flex flex-col gap-6">
                <Facts
                  items={[
                    {
                      label: copy.legal.completed,
                      value: copy.legal.completedOn(
                        formatDateTime(audit.completed_at),
                        staffLabel(audit.completed_by, me),
                      ),
                    },
                    {
                      label: copy.legal.effectiveFrom,
                      value: audit.effective_from ? formatDate(audit.effective_from) : copy.common.unknown,
                    },
                    {
                      label: copy.legal.certificateText,
                      value: <span className="whitespace-pre-wrap">{audit.certificate_text}</span>,
                    },
                    {
                      label: copy.legal.signedCopy,
                      value: audit.has_file ? (
                        <a href={certificateHref(audit.id)} download>
                          {copy.legal.download}
                        </a>
                      ) : (
                        copy.legal.signedCopyNone
                      ),
                    },
                  ]}
                />
                {managing ? <CertificateUpload audit={audit} /> : null}
                <Rows audit={audit} />
              </div>
            ) : managing ? (
              <div className="flex flex-col gap-6">
                <AuditForm audit={audit} />
                <div className="flex flex-col gap-2 border-t border-border pt-4">
                  <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">{copy.legal.completeText}</p>
                  <div>
                    <CompleteAudit audit={audit} />
                  </div>
                </div>
              </div>
            ) : (
              <Rows audit={audit} />
            )}
          </Section>
        )}
      </div>
    </>
  );
}
