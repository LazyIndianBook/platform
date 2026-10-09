// /content/papers/<id>/: one paper (GET content/papers/{id}/): its facts, on the site or off it (staff.publish_paper;
// taking it off is typed), its questions and solutions as a tree with their states, and the editor of the one chosen
// (?solution=<id> or ?question=<id>: GET content/solutions|questions/{id}/) with its history; the paper's QR code
// (GET …/qr/, for a print run when one is named: ?printing=; refused, in the API's words, while the site's address is
// not a public https one); notes and the audit trail beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { Editor } from "@/components/modules/content/editor";
import { History } from "@/components/modules/content/history";
import { PaperPublish } from "@/components/modules/content/paper-publish";
import { ContentState } from "@/components/modules/content/tables";
import { Section } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, recordId, type SearchParams, staffPage } from "@/lib/api/page";
import {
  type ContentPaperDetail,
  draftOf,
  getPaper,
  getPaperQr,
  getQuestion,
  getSolution,
  listHistory,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.papers.title };

const words = copy.content;
type Row = ContentPaperDetail["tree"][number];

/** The tree's rows under their printed group headings. */
function groups(rows: Row[]): { heading: string; rows: Row[] }[] {
  const out: { heading: string; rows: Row[] }[] = [];
  for (const row of rows) {
    const heading = [row.part_label, row.group_label].filter(Boolean).join(" · ");
    const last = out.at(-1);
    if (last && last.heading === heading) last.rows.push(row);
    else out.push({ heading, rows: [row] });
  }
  return out;
}

export default async function PaperPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const search = await searchParams;
  const here = `/content/papers/${encodeURIComponent(id)}/`;
  const { manifest, transport, path } = await staffPage(here);
  const paper = await attempt(getPaper(recordId(id), transport), path, "404");
  const back = { href: "/content/papers/", label: words.papers.title };
  if (paper instanceof ApiError)
    return (
      <RecordPage title={words.papers.title} back={back}>
        <Problem error={paper} />
      </RecordPage>
    );
  const solutionId = /^\d+$/.test(param(search, "solution")) ? Number(param(search, "solution")) : null;
  const questionId = /^\d+$/.test(param(search, "question")) ? Number(param(search, "question")) : null;
  const kind = solutionId ? "solutions" : questionId ? "questions" : null;
  const chosen = solutionId ?? questionId;
  const [qr, record, versions] = await Promise.all([
    attempt(getPaperQr(paper.id, param(search, "printing"), transport), path),
    solutionId && has(manifest, P.solutionsView)
      ? attempt(getSolution(solutionId, transport), path)
      : questionId && has(manifest, P.questionsView)
        ? attempt(getQuestion(questionId, transport), path)
        : null,
    kind && chosen ? attempt(listHistory(kind, chosen, param(search, "versions"), transport), path) : null,
  ]);
  const editLink = (field: "solution" | "question", recordKey: number) => `${here}?${field}=${recordKey}#editor`;
  return (
    <RecordPage
      eyebrow={`${paper.code} · ${labelOf(words.subjects, paper.subject_code)}`}
      title={paper.title}
      back={back}
      status={
        <>
          {paper.is_published ? null : <StatusChip tone="stopped">{words.offSite}</StatusChip>}
          {paper.is_sample ? <StatusChip tone="good">{words.sample}</StatusChip> : null}
          {paper.drafts ? <StatusChip tone="waiting">{words.changed}</StatusChip> : null}
        </>
      }
      actions={has(manifest, P.papersPublish) ? <PaperPublish paper={paper} /> : undefined}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "content.paper", target_id: String(paper.id) },
        note: { type: "content.paper", id: String(paper.id) },
      })}
    >
      <Facts
        items={[
          { label: words.papers.facts.book, value: paper.book_title },
          { label: words.papers.columns.tier, value: labelOf(words.tiers, paper.tier) },
          { label: words.papers.facts.marks, value: paper.full_marks },
          { label: words.papers.facts.pass, value: paper.pass_marks },
          { label: words.papers.facts.time, value: paper.time_text },
          { label: words.papers.facts.questions, value: paper.questions },
          { label: words.papers.facts.drafts, value: paper.drafts },
        ]}
      />

      {record && kind ? (
        <Section
          id="editor"
          title={
            kind === "solutions" && "question_label" in record
              ? words.editor.solutionTitle(`${paper.code} ${record.question_label}`)
              : words.editor.questionTitle(`${paper.code} ${"label" in record ? record.label : ""}`)
          }
          actions={
            <Link href={here} className="text-[15px] font-semibold">
              {words.editor.close}
            </Link>
          }
        >
          {record instanceof ApiError ? (
            <Problem error={record} />
          ) : (
            <>
              {"question_text" in record ? (
                <p className="m-0 max-w-[70ch] text-[15px] text-muted-foreground">
                  {record.question_text.slice(0, 280)}
                  {record.question_text.length > 280 ? "…" : ""}
                </p>
              ) : null}
              <Editor
                key={`${record.id}-${record.state}-${JSON.stringify(draftOf(record))}`}
                kind={kind}
                record={record}
              />
              {versions && !(versions instanceof ApiError) && chosen ? (
                <Section
                  id="history"
                  title={words.editor.history}
                  lead={words.editor.historyLead}
                  className="mt-6 flex flex-col gap-3"
                >
                  <History kind={kind} id={chosen} page={versions} />
                </Section>
              ) : versions instanceof ApiError ? (
                <Problem error={versions} />
              ) : null}
            </>
          )}
        </Section>
      ) : null}

      <Section id="tree" title={words.papers.tree} lead={words.papers.treeLead}>
        {paper.tree.length ? (
          <div className="flex flex-col gap-5">
            {groups(paper.tree).map((group, index) => (
              <div key={`${group.heading}-${index}`} className="flex flex-col gap-1">
                {group.heading ? (
                  <p className="m-0 text-sm font-semibold text-muted-foreground">{group.heading}</p>
                ) : null}
                <ul className="m-0 flex list-none flex-col p-0">
                  {group.rows.map((row) => (
                    <li
                      key={row.id}
                      className="grid gap-x-4 gap-y-1.5 border-t border-border py-2.5 min-[720px]:grid-cols-[5rem_minmax(0,1fr)_auto]"
                    >
                      <span className="font-mono text-[15px] font-semibold">{row.label}</span>
                      <span className="flex min-w-0 flex-col gap-1">
                        <span className="text-[15px] break-words">{row.preview}</span>
                        <span className="flex flex-wrap items-center gap-1.5">
                          {row.is_published ? null : <StatusChip tone="stopped">{words.gone}</StatusChip>}
                          {row.state !== "published" ? <ContentState state={row.state ?? "draft"} /> : null}
                          {row.solution && row.solution.state !== "published" ? (
                            <ContentState state={row.solution.state ?? "draft"} />
                          ) : null}
                        </span>
                      </span>
                      <span className="flex flex-wrap items-center gap-x-4">
                        {row.solution ? (
                          <Link
                            href={editLink("solution", row.solution.id)}
                            aria-current={solutionId === row.solution.id ? "true" : undefined}
                            className="inline-flex min-h-11 items-center font-semibold"
                          >
                            {words.papers.editSolution}
                            <span className="sr-only"> {row.label}</span>
                          </Link>
                        ) : (
                          <span className="text-sm text-muted-foreground">{words.papers.noSolution}</span>
                        )}
                        <Link
                          href={editLink("question", row.id)}
                          aria-current={questionId === row.id ? "true" : undefined}
                          className="inline-flex min-h-11 items-center"
                        >
                          {words.papers.editQuestion}
                          <span className="sr-only"> {row.label}</span>
                        </Link>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{words.papers.noQuestions}</p>
        )}
      </Section>

      <Section id="qr" title={words.papers.qr} lead={words.papers.qrLead}>
        <form method="get" action={`${here}#qr`} className="mb-5 flex flex-wrap items-end gap-3">
          <Field id="qr-printing" label={words.papers.qrPrinting} optional help={words.papers.qrPrintingHelp}>
            <Input name="printing" defaultValue={param(search, "printing")} autoComplete="off" className="font-mono" />
          </Field>
          <Button type="submit" variant="secondary" size="sm">
            {words.papers.qrShow}
          </Button>
        </form>
        {qr instanceof ApiError ? (
          <Problem error={qr} />
        ) : (
          <div className="flex flex-wrap items-center gap-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={qr.png}
              alt={words.papers.qrAlt(paper.code)}
              width={164}
              height={164}
              className="border border-border bg-card"
            />
            <div className="flex flex-col gap-2 [&>*]:m-0">
              <p className="font-mono text-[15px] break-all">{qr.url}</p>
              <a href={qr.png} download={`${paper.code}.png`} className="font-semibold">
                {words.papers.qrDownload}
              </a>
            </div>
          </div>
        )}
      </Section>
    </RecordPage>
  );
}
