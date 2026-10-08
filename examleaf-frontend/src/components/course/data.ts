// The revision course's pages on the website (proposed, ExamLeaf A - Learning (LMS).dc.html): only while config/ has
// web_course on, only for a signed-in student, each chapter by its subject's key and number (/revision/physics/3/).
// What is open or locked is always the API's answer (learn/chapters/<id>/ and the 403s of clips, cards and the quiz);
// nothing here decides it.
import "server-only";

import { notFound } from "next/navigation";
import { cache } from "react";

import { getSubjects, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError, unavailableError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, publicFetch, serverApi } from "@/lib/api/server";
import { requireUser } from "@/lib/auth/session";
import { SUBJECTS } from "@/lib/site";

export type ChapterDetail = components["schemas"]["ChapterDetail"];

/** No course page while config/ has web_course off, or cannot be read: a 404 (and no link to it is drawn). */
export async function requireCourse() {
  if (!(await getConfig())?.web_course) notFound();
}

export const chapterPath = (key: string, number: string | number) => `/revision/${key}/${number}/`;

/** A call the page cannot do without: the "cannot be reached" error (a 500, error.tsx) rather than a made-up page. */
const failed = (error: unknown): never => {
  throw error instanceof ApiError ? unavailableError() : error;
};

/** /revision/<key>/<number>/'s chapter as the API answers it for the signed-in student (its flags, its clips with
 *  free, locked and completed): a 404 for an unknown subject or number, or a chapter whose revision is not out. The
 *  page and its metadata share one call per request. */
export const loadChapter = cache(async (key: string, number: string, path: string) => {
  await requireCourse();
  await requireUser(path);
  const code = Object.keys(SUBJECTS).find((subject) => SUBJECTS[subject].key === key);
  if (!code || !/^\d{1,4}$/.test(number)) notFound();
  const subject = (await getSubjects().catch(failed)).find((row) => row.code === code);
  if (!subject) notFound();
  const list = await unwrap(
    serverApi.GET("/api/v1/learn/chapters/", {
      params: { query: { subject: subject.id, page_size: 200 } },
      ...publicFetch("chapters"),
    }),
  ).catch(failed);
  const row = list.results.find((chapter) => chapter.number === Number(number));
  if (!row?.has_revision) notFound();
  const chapter = await settle(
    unwrap(
      serverApi.GET("/api/v1/learn/chapters/{id}/", { params: { path: { id: row.id } }, ...(await personalFetch()) }),
    ),
    path,
  );
  if (chapter instanceof ApiError) return chapter.status === 404 ? notFound() : failed(chapter);
  return { subject, chapter };
});
