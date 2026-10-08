// /revision/<subject key>/<chapter number>/cards/ (proposed, only while config/ has web_course on): the chapter's flash
// cards in focus mode (Flash cards, Phone flash card). learn/flash-cards/?chapter= answers them, or a 403 when they are
// not open to the student, shown in the API's words with the way back to the book-code form. Fronts and backs are
// drawn here (Markdown, maths); each answer goes to the API as a card review (CardDeck). Never indexed.
import "katex/dist/katex.min.css";
import "../course.css";

import type { Metadata } from "next";

import { deckCards, NothingToGoThrough } from "@/components/course/chapter";
import { chapterPath, loadChapter } from "@/components/course/data";
import { CardDeck } from "@/components/course/flash-cards";
import { FocusBar } from "@/components/course/focus-bar";
import { getMe, settle } from "@/lib/api/account";
import { ApiError, unavailableError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";

type Props = { params: Promise<{ subject: string; chapter: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { subject, chapter } = await params;
  const { chapter: found } = await loadChapter(subject, chapter, `${chapterPath(subject, chapter)}cards/`);
  return { title: `Flash cards · ${found.title}`, robots: { index: false, follow: false } };
}

export default async function CardsPage({ params }: Props) {
  const { subject: key, chapter: number } = await params;
  const back = chapterPath(key, number);
  const path = `${back}cards/`;
  const { chapter } = await loadChapter(key, number, path);
  const [cards, me] = await Promise.all([
    settle(
      unwrap(
        serverApi.GET("/api/v1/learn/flash-cards/", {
          params: { query: { chapter: chapter.id, page_size: 200 } },
          ...(await personalFetch()),
        }),
      ),
      path,
    ),
    getMe().catch(() => null),
  ]);
  if (cards instanceof ApiError && cards.unavailable) throw unavailableError();
  const title = `${chapter.title} · Flash cards`;

  return (
    <div data-course-focus="" className="course-focus">
      {cards instanceof ApiError || !cards.results.length ? (
        <>
          <FocusBar title={title} short="Flash cards" close={back} />
          <NothingToGoThrough
            refusal={cards instanceof ApiError ? cards : null}
            empty="No flash cards in this chapter yet"
            back={back}
          />
        </>
      ) : (
        <CardDeck
          title={title}
          cards={deckCards(cards.results)}
          close={{ href: back, label: "Back to the chapter" }}
          consentPending={Boolean(me?.consent_pending)}
        />
      )}
    </div>
  );
}
