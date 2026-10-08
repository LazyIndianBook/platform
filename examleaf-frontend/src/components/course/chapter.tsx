// A chapter page's parts (Chapter, Chapter locked, Phone chapter), drawn from learn/chapters/<id>/ and learn/clips/<id>/
// without any state: the clip list (watched, playing, free or locked, as the API says), the clip's notes and the Board's
// questions it prepares for, and the ways to practise. Server components: the notes' maths is drawn here.
import { cn } from "cn";
import Link from "next/link";

import { MarkdownBlock, MarkdownInline } from "@/components/solutions/markdown";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import type { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { shortCode } from "@/lib/site";

type ClipRow = components["schemas"]["ClipRow"];
type Clip = components["schemas"]["Clip"];
type Chapter = components["schemas"]["ChapterDetail"];
/** Clip.questions (the schema has no shape for them): the paper, the question's label, its page. */
type BoardQuestion = { paper: string; label: string; web_url: string };

export const KIND: Record<components["schemas"]["ClipKindEnum"], string> = {
  concept: "Concept",
  trick: "Trick",
  shortcut: "Shortcut",
  formula: "Formula",
  pattern: "Pattern",
  mistake: "Common mistake",
  pyq: "Previous-year q.",
};

export const minutes = (seconds: number) => `${Math.max(1, Math.round(seconds / 60))} min`;
export const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

const rowLink = "text-foreground no-underline hover:bg-paper-2 hover:text-foreground";

/** An open chapter's clips: each a link that plays it here; ✓ watched to the end, ▶ playing now. */
export function ClipList({ clips, current, path }: { clips: ClipRow[]; current: number | null; path: string }) {
  return (
    <ol aria-label="Clips" className="m-0 list-none border-t-[1.5px] border-foreground p-0">
      {clips.map((clip, index) => {
        const playing = clip.id === current;
        return (
          <li key={clip.id}>
            <Link
              href={`${path}?clip=${clip.id}`}
              aria-current={playing ? "true" : undefined}
              className={cn(
                "grid min-h-[52px] grid-cols-[36px_minmax(0,1fr)_120px_56px] items-center gap-3 border-b border-border px-2 py-2 text-[15px] leading-snug",
                "max-nav:min-h-12 max-nav:grid-cols-[28px_minmax(0,1fr)_48px] max-nav:gap-2 max-nav:px-0 max-nav:text-sm",
                rowLink,
                playing && "bg-card font-bold hover:bg-card",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "font-mono text-sm font-semibold max-nav:text-[13px]",
                  playing ? "text-red-ink" : clip.completed ? "text-easy" : "text-muted-foreground",
                )}
              >
                {playing ? "▶" : clip.completed ? "✓" : String(index + 1).padStart(2, "0")}
              </span>
              <span className={cn("min-w-0", !playing && "font-medium")}>
                {playing ? <span className="sr-only">Playing: </span> : null}
                {clip.title}
                {clip.completed ? <span className="sr-only"> (watched)</span> : null}
              </span>
              <span className="font-mono text-xs text-muted-foreground uppercase max-nav:hidden">
                {KIND[clip.kind ?? "concept"]}
              </span>
              <span className="text-right font-mono text-[13px] font-medium text-muted-foreground max-nav:text-xs">
                {minutes(clip.duration)}
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

/** A chapter that is not open: its free clips (links that play them here) and its locked ones, as the API marks them. */
export function LockedList({ clips, current, path }: { clips: ClipRow[]; current: number | null; path: string }) {
  const row =
    "grid min-h-[50px] grid-cols-[36px_minmax(0,1fr)_140px_56px] items-center gap-3 border-b border-border py-2 text-[15px] leading-snug max-nav:grid-cols-[28px_minmax(0,1fr)_64px_44px] max-nav:gap-2 max-nav:text-sm";
  return (
    <ol aria-label="Clips" className="m-0 list-none border-t-[1.5px] border-foreground p-0">
      {clips.map((clip) => {
        const cells = (
          <>
            <span
              aria-hidden="true"
              className={cn("font-mono text-[13px] font-semibold", clip.locked ? "text-input" : "text-red-ink")}
            >
              {clip.locked ? "—" : "▶"}
            </span>
            <span className="min-w-0 font-semibold">{clip.title}</span>
            <span className="font-mono text-xs font-medium">{clip.locked ? "LOCKED" : "FREE"}</span>
            <span className="text-right font-mono text-[13px] font-medium">{minutes(clip.duration)}</span>
          </>
        );
        return (
          <li key={clip.id}>
            {clip.locked ? (
              <div className={cn(row, "text-muted-foreground")}>{cells}</div>
            ) : (
              <Link
                href={`${path}?clip=${clip.id}`}
                aria-current={clip.id === current ? "true" : undefined}
                className={cn(row, rowLink, clip.id === current && "bg-card")}
              >
                {cells}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** The clip's notes (Markdown, maths drawn here) and the Board's questions it prepares for, each to its solutions. */
export function ClipNotes({ clip }: { clip: Clip }) {
  const questions = clip.questions as unknown as BoardQuestion[];
  if (!clip.notes && !questions.length) return null;
  const heading = "font-head text-[22px] leading-[1.2] tracking-normal";
  return (
    <div className="grid gap-6 nav:grid-cols-2">
      {clip.notes ? (
        <section aria-labelledby="clip-notes" className="flex min-w-0 flex-col gap-2.5">
          <h2 id="clip-notes" className={heading}>
            Notes for this clip
          </h2>
          <div className="font-read text-[17px] leading-[1.7] text-ink/85 [&_p]:m-0 [&_p+p]:mt-3">
            <MarkdownBlock>{clip.notes}</MarkdownBlock>
          </div>
        </section>
      ) : null}
      {questions.length ? (
        <section aria-labelledby="clip-questions" className="flex min-w-0 flex-col gap-2.5">
          <h2 id="clip-questions" className={heading}>
            The Board asked this
          </h2>
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
            {questions.map((question) => (
              <li key={`${question.paper} ${question.label}`}>
                <Link
                  href={`/s/${encodeURIComponent(question.paper)}/`}
                  className="grid min-h-11 grid-cols-[72px_minmax(0,1fr)] gap-2.5 border border-border bg-card p-3 text-[15px] leading-normal text-foreground no-underline hover:border-foreground hover:text-foreground"
                >
                  <span className="font-mono text-[13px] leading-normal font-semibold text-red-ink">
                    {shortCode(question.paper)} {question.label}
                  </span>
                  <strong className="text-primary">Open its solution →</strong>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

const tile = "flex min-h-11 flex-col gap-1 p-4 [&_p]:m-0";

/** The ways to practise the chapter: its flash cards and quiz where the API says they are open, and the must-do note. */
export function Practice({ chapter, path }: { chapter: Chapter; path: string }) {
  const cardsOpen = chapter.entitled || chapter.free_cards;
  const linkTile = cn(
    tile,
    "border-[1.5px] border-foreground bg-card text-foreground no-underline hover:bg-paper-2 hover:text-foreground",
  );
  const quietTile = cn(tile, "border border-border text-muted-foreground");
  const name = "font-head text-xl leading-[1.2] font-semibold text-foreground";
  const line = "text-sm leading-snug text-muted-foreground";
  return (
    <div className="grid grid-cols-3 gap-3 max-nav:hidden">
      {cardsOpen && chapter.flash_cards ? (
        <Link href={`${path}cards/`} className={linkTile}>
          <strong className={name}>Flash cards</strong>
          <span className={line}>{plural(chapter.flash_cards, "card")}</span>
        </Link>
      ) : (
        <div className={quietTile}>
          <strong className={name}>Flash cards</strong>
          <span className={line}>{chapter.flash_cards ? "Open with the course" : "None in this chapter yet"}</span>
        </div>
      )}
      {chapter.entitled && chapter.quiz_items ? (
        <Link href={`${path}quiz/`} className={linkTile}>
          <strong className={name}>Quiz</strong>
          <span className={line}>{plural(chapter.quiz_items, "one-mark question")}</span>
        </Link>
      ) : (
        <div className={quietTile}>
          <strong className={name}>Quiz</strong>
          <span className={line}>{chapter.quiz_items ? "Open with the course" : "None in this chapter yet"}</span>
        </div>
      )}
      {chapter.must_do ? (
        <div className={quietTile}>
          <strong className={name}>Must-do</strong>
          <span className={line}>
            <MarkdownInline>{chapter.must_do}</MarkdownInline>
          </span>
        </div>
      ) : null}
    </div>
  );
}

/** Flash cards as CardDeck takes them: fronts and backs drawn here (Markdown, maths). */
export function deckCards(cards: components["schemas"]["FlashCard"][]) {
  return cards.map((card) => ({
    id: card.id,
    front: <MarkdownBlock>{card.front}</MarkdownBlock>,
    back: <MarkdownBlock>{card.back}</MarkdownBlock>,
  }));
}

/** Quiz items as QuizRun takes them (never an answer: the list has none): the question and, for multiple choice, the
 *  options, drawn here. */
export function quizQuestions(items: components["schemas"]["QuizItem"][]) {
  return items.map((item) => ({
    id: item.id,
    kind: item.kind,
    text: <MarkdownBlock>{item.text}</MarkdownBlock>,
    options:
      item.kind === "mcq" && Array.isArray(item.options)
        ? item.options.map((option, index) => <MarkdownInline key={index}>{String(option)}</MarkdownInline>)
        : [],
  }));
}

/** A focus page with nothing to go through: the API's refusal in its own words (not open to this student: the chapter
 *  page has the book-code form), or none in the chapter yet. */
export function NothingToGoThrough({
  refusal,
  empty,
  back,
}: {
  refusal: ApiError | null;
  empty: string;
  back: string;
}) {
  return (
    <div className="mx-auto w-full max-w-[624px] px-12 py-10 max-nav:px-4 max-nav:py-6">
      <EmptyState
        art={refusal ? "missing" : "sheet"}
        title={refusal ? "Not open to you yet" : empty}
        action={
          <Link href={back} className={buttonVariants({ variant: "primary" })}>
            Back to the chapter
          </Link>
        }
        after={refusal?.status === 403 ? <Link href="/shop/">Get the course in the shop</Link> : undefined}
      >
        {refusal ? <p>{refusal.message}</p> : null}
      </EmptyState>
    </div>
  );
}

/** The phone's two buttons under the clip (Phone chapter), for what is open. */
export function PracticeButtons({ chapter, path }: { chapter: Chapter; path: string }) {
  const button =
    "flex min-h-12 items-center justify-center rounded-btn border-[1.5px] border-foreground font-bold text-foreground no-underline hover:bg-secondary-hover hover:text-foreground";
  const cards = (chapter.entitled || chapter.free_cards) && chapter.flash_cards > 0;
  const quiz = chapter.entitled && chapter.quiz_items > 0;
  if (!cards && !quiz) return null;
  return (
    <div className="mt-1.5 grid grid-cols-2 gap-2 nav:hidden">
      {cards ? (
        <Link href={`${path}cards/`} className={button}>
          Cards
        </Link>
      ) : null}
      {quiz ? (
        <Link href={`${path}quiz/`} className={button}>
          Quiz
        </Link>
      ) : null}
    </div>
  );
}
