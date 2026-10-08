"use client";

// A deck of flash cards (Flash cards, Phone flash card): the front, then the back, then "Not yet" or "I knew it",
// each answer saved as a card review (POST learn/flash-cards/<id>/review/) before the next card comes; the API's
// reviews decide when a card comes back (Revise again). Space turns the card, 1 and 2 answer it (and the buttons, for
// touch). The cards' Markdown and maths were drawn on the server. While a parent's consent is awaited the API saves
// nothing, so the deck only turns and says so.
import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { ConsentPending } from "@/components/account/parts";
import { useAction } from "@/components/account/use-action";
import { Button, buttonVariants } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import { api, personal } from "@/lib/api/client";
import { focusHere } from "@/lib/utils";

import { Count, FocusBar } from "./focus-bar";

export type Card = { id: number; front: React.ReactNode; back: React.ReactNode };
type Go = { href: string; label: string };

const keyHint = "ml-2.5 font-mono text-[13px] font-medium opacity-75";
const NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
export const inWords = (count: number) => NUMBERS[count] ?? String(count);

export function CardDeck({
  title,
  cards,
  close,
  next,
  consentPending = false,
}: {
  title: string;
  cards: Card[];
  /** Close, and the way back from the last card. */
  close: Go;
  /** What follows the deck, if anything (Revise again: its quiz questions). */
  next?: Go;
  consentPending?: boolean;
}) {
  const [at, setAt] = useState(0);
  const [turned, setTurned] = useState(false);
  const [known, setKnown] = useState(0);
  const { run, busy, error } = useAction();
  const sending = useRef(false);
  const face = useRef<HTMLDivElement>(null);
  const [moved, setMoved] = useState(0); // after a turn or an answer, focus follows the card (not on the first load)
  const card = cards[at];
  const done = at >= cards.length;

  useEffect(() => {
    if (moved) focusHere(face.current);
  }, [moved]);

  const turn = () => {
    setTurned(true);
    setMoved((count) => count + 1);
  };

  async function answer(knew: boolean) {
    if (!card || !turned || sending.current) return;
    sending.current = true;
    const saved =
      consentPending ||
      (await run(() =>
        personal(
          api.POST("/api/v1/learn/flash-cards/{id}/review/", {
            params: { path: { id: card.id } },
            body: { known: knew },
          }),
        ),
      ));
    sending.current = false;
    if (!saved) return;
    if (knew) setKnown((count) => count + 1);
    setTurned(false);
    setAt((index) => index + 1);
    setMoved((count) => count + 1);
  }

  // Space and 1/2 anywhere but in a box being typed in; Space on a focused button is that button's own press
  const onKey = useEffectEvent((event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (done || event.altKey || event.ctrlKey || event.metaKey) return;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key === " " && !turned && !target?.closest("button")) {
      event.preventDefault();
      turn();
    } else if (turned && (event.key === "1" || event.key === "2")) {
      event.preventDefault();
      void answer(event.key === "2");
    }
  });
  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const share = done ? 100 : Math.round((100 * (at + 1)) / cards.length);
  const notYet = at - known;

  return (
    <>
      <FocusBar
        title={title}
        short="Flash cards"
        close={close.href}
        status={done ? "Done" : <Count at={at + 1} of={cards.length} noun="Card" />}
      />
      <div aria-hidden="true" className="h-1 bg-rule-soft">
        <span className="block h-full bg-primary" style={{ width: `${share}%` }} />
      </div>
      <div className="mx-auto flex w-full max-w-[624px] flex-col gap-6 px-12 pt-10 pb-11 max-nav:gap-[18px] max-nav:px-4 max-nav:pt-6 max-nav:pb-7 [&_p]:m-0">
        {consentPending ? <ConsentPending what="you can go through the cards, but your answers are not saved" /> : null}
        {done ? (
          <div ref={face} className="flex flex-col gap-3.5">
            <h2 className="text-[34px] leading-[1.05]">
              You knew {known} of {cards.length}
            </h2>
            <p className="text-[15px] leading-[1.55] text-ink/85">
              {consentPending
                ? "Nothing was saved: your parent or guardian has not confirmed your account yet."
                : notYet
                  ? `The ${inWords(notYet)} you marked "Not yet" ${notYet === 1 ? "comes" : "come"} back in Revise again tomorrow.`
                  : "Every card known."}
            </p>
            <div className="flex flex-wrap gap-2.5">
              <Link href={(next ?? close).href} className={buttonVariants({ className: "flex-1" })}>
                {(next ?? close).label}
              </Link>
              <Button
                variant="secondary"
                onClick={() => {
                  setAt(0);
                  setKnown(0);
                  setTurned(false);
                }}
              >
                Go through them again
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div
              ref={face}
              aria-live="polite"
              className="flex min-h-[300px] flex-col justify-between gap-6 border-[1.5px] border-foreground bg-card p-8 shadow-[6px_6px_0_var(--rule-soft)] max-nav:min-h-[360px] max-nav:p-[22px] max-nav:shadow-[5px_5px_0_var(--rule-soft)]"
            >
              <p className="font-mono text-xs leading-none font-semibold tracking-[0.08em] text-red-ink max-nav:text-[11px]">
                {turned ? "BACK" : "FRONT"}
              </p>
              <div className="font-read text-[28px] leading-[1.45] text-pretty max-nav:text-[23px] max-nav:leading-normal [&_p+p]:mt-3">
                {turned ? card.back : card.front}
              </div>
              <div className="text-sm text-muted-foreground max-nav:text-[13px] [&_p]:inline">
                {turned ? <>Front: {card.front}</> : "Say the answer to yourself, then turn the card."}
              </div>
            </div>
            {turned ? (
              <div className="grid grid-cols-2 gap-3 max-nav:gap-2.5">
                <Button
                  variant="secondary"
                  className="min-h-14 text-[17px]"
                  aria-keyshortcuts="1"
                  busy={busy}
                  onClick={() => void answer(false)}
                >
                  Not yet
                  <span aria-hidden="true" className={`${keyHint} text-muted-foreground opacity-100 max-nav:hidden`}>
                    1
                  </span>
                </Button>
                <Button
                  className="min-h-14 text-[17px]"
                  aria-keyshortcuts="2"
                  busy={busy}
                  onClick={() => void answer(true)}
                >
                  I knew it
                  <span aria-hidden="true" className={`${keyHint} max-nav:hidden`}>
                    2
                  </span>
                </Button>
              </div>
            ) : (
              <Button className="min-h-14 text-[17px]" aria-keyshortcuts="Space" onClick={turn}>
                Show the back
                <span aria-hidden="true" className={`${keyHint} max-nav:hidden`}>
                  Space
                </span>
              </Button>
            )}
            {error?.code === "consent_pending" ? (
              <ConsentPending what="you can go through the cards, but your answers are not saved" />
            ) : error ? (
              <FieldError role="alert">{error.message}</FieldError>
            ) : null}
            <p className="text-sm leading-normal text-muted-foreground max-nav:hidden">
              {turned
                ? 'Keyboard: 1 Not yet, 2 I knew it. "Not yet" cards come back in Revise again.'
                : "Keyboard: Space turns the card. Each answer is saved and decides when the card comes back."}
            </p>
          </>
        )}
      </div>
    </>
  );
}
