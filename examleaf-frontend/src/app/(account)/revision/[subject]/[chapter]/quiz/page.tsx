// /revision/<subject key>/<chapter number>/quiz/ (proposed, only while config/ has web_course on): the chapter's
// one-mark quiz in focus mode (Quiz question, Quiz feedback, Quiz result, Phone quiz). learn/quiz/?chapter= lists the
// questions without their answers, or a 403 when the quiz is not open to the student (shown in the API's words). The
// questions and options are drawn here (Markdown, maths); every answer is checked by the server (QuizRun). Never indexed.
import "katex/dist/katex.min.css";
import "../course.css";

import type { Metadata } from "next";

import { NothingToGoThrough, quizQuestions } from "@/components/course/chapter";
import { chapterPath, loadChapter } from "@/components/course/data";
import { FocusBar } from "@/components/course/focus-bar";
import { QuizRun } from "@/components/course/quiz";
import { getMe, settle } from "@/lib/api/account";
import { ApiError, unavailableError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";

type Props = { params: Promise<{ subject: string; chapter: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { subject, chapter } = await params;
  const { chapter: found } = await loadChapter(subject, chapter, `${chapterPath(subject, chapter)}quiz/`);
  return { title: `Quiz · ${found.title}`, robots: { index: false, follow: false } };
}

export default async function QuizPage({ params }: Props) {
  const { subject: key, chapter: number } = await params;
  const back = chapterPath(key, number);
  const path = `${back}quiz/`;
  const { chapter } = await loadChapter(key, number, path);
  const [quiz, me] = await Promise.all([
    settle(
      unwrap(
        serverApi.GET("/api/v1/learn/quiz/", {
          params: { query: { chapter: chapter.id, page_size: 200 } },
          ...(await personalFetch()),
        }),
      ),
      path,
    ),
    getMe().catch(() => null),
  ]);
  if (quiz instanceof ApiError && quiz.unavailable) throw unavailableError();
  const title = `${chapter.title} · Quiz`;

  return (
    <div data-course-focus="" className="course-focus">
      {quiz instanceof ApiError || !quiz.results.length ? (
        <>
          <FocusBar title={title} short="Quiz" close={back} />
          <NothingToGoThrough
            refusal={quiz instanceof ApiError ? quiz : null}
            empty="No quiz questions in this chapter yet"
            back={back}
          />
        </>
      ) : (
        <QuizRun
          title={title}
          questions={quizQuestions(quiz.results)}
          close={{ href: back, label: "Back to the chapter" }}
          draftKey={`examleaf:course:quiz:${chapter.id}`}
          consentPending={Boolean(me?.consent_pending)}
        />
      )}
    </div>
  );
}
