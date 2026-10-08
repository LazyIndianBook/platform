// /revision/<subject key>/<chapter number>/ (proposed, only while config/ has web_course on): a chapter of the revision
// course for the signed-in student (Chapter, Chapter locked, Phone chapter). learn/chapters/<id>/ says what is open. An
// open chapter plays its clips here (?clip=<id> picks one, else the first not yet watched) with the clip's notes, the
// Board's questions and the ways to practise; a chapter that is not open lists its free and locked clips beside the
// book-code form, and plays a free clip when one is picked. Never indexed; never cached (src/proxy.ts).
import "katex/dist/katex.min.css";
import "./course.css";

import type { Metadata } from "next";

import { ConsentPending } from "@/components/account/parts";
import { ClipList, ClipNotes, KIND, LockedList, plural, Practice, PracticeButtons } from "@/components/course/chapter";
import { chapterPath, loadChapter } from "@/components/course/data";
import { ChapterPlayer } from "@/components/course/player";
import { RedeemCard } from "@/components/course/redeem-card";
import { Alert } from "@/components/ui/alert";
import { Marks, Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { getMe, settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";

type Props = {
  params: Promise<{ subject: string; chapter: string }>;
  searchParams: Promise<{ clip?: string | string[] }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { subject, chapter } = await params;
  const { chapter: found } = await loadChapter(subject, chapter, chapterPath(subject, chapter));
  return { title: `Ch. ${found.number} ${found.title}`, robots: { index: false, follow: false } };
}

export default async function ChapterPage({ params, searchParams }: Props) {
  const { subject: key, chapter: number } = await params;
  const path = chapterPath(key, number);
  const { subject, chapter } = await loadChapter(key, number, path);
  const clips = chapter.revision.clips;
  const asked = Number([(await searchParams).clip].flat()[0]);
  // the clip asked for if it plays for this student; else, in an open chapter, the first not yet watched
  const current =
    clips.find((clip) => clip.id === asked && !clip.locked) ??
    (chapter.entitled ? (clips.find((clip) => !clip.completed) ?? clips[0]) : undefined);
  const [clip, me] = await Promise.all([
    current
      ? settle(
          unwrap(
            serverApi.GET("/api/v1/learn/clips/{id}/", {
              params: { path: { id: current.id } },
              ...(await personalFetch()),
            }),
          ),
          `${path}?clip=${current.id}`,
        )
      : null,
    getMe().catch(() => null),
  ]);
  const consentPending = Boolean(me?.consent_pending);
  const watched = clips.filter((row) => row.completed).length;
  const marks = Number(chapter.weight ?? 0);
  const trail = [
    { label: "Revision course", href: "/revision/" },
    { label: subject.name },
    { label: `Chapter ${chapter.number}` },
  ];

  const player = current ? (
    <div className="flex min-w-0 flex-col gap-3 [&_p]:m-0">
      {clip instanceof ApiError || !clip ? (
        <Alert variant="warning" title="This clip cannot be played here">
          <p>{clip?.message}</p>
        </Alert>
      ) : (
        <ChapterPlayer clip={clip} save={!consentPending} />
      )}
      <p className="flex justify-between gap-3 font-mono text-[11px] leading-none font-medium tracking-[0.08em] text-red-ink uppercase">
        <span>
          <span className="nav:hidden">Ch.{chapter.number} · </span>
          Clip {clips.indexOf(current) + 1} of {clips.length}
          <span className="max-nav:hidden"> · {KIND[current.kind ?? "concept"]}</span>
        </span>
        <span className="nav:hidden">
          <span aria-hidden="true">[{marks}]</span>
          <span className="sr-only">{marks} Board marks</span>
        </span>
      </p>
      <h2 className="font-head text-2xl leading-[1.2] tracking-normal max-nav:text-[21px]">{current.title}</h2>
      {consentPending ? null : (
        <p className="text-sm leading-normal text-muted-foreground max-nav:hidden">
          Progress is saved as you watch, so the app and the website stay in step.
        </p>
      )}
      <PracticeButtons chapter={chapter} path={path} />
    </div>
  ) : null;

  if (!chapter.entitled) {
    return (
      <Sheet margin={`Ch.${chapter.number}`} className="course-sheet" bodyClassName="nav:pt-8 nav:pb-16">
        <div className="grid items-start gap-12 max-nav:gap-8 nav:grid-cols-[minmax(0,1fr)_400px]">
          <div className="flex min-w-0 flex-col gap-3.5 [&_p]:m-0">
            <Breadcrumb trail={trail} className="[&_ol]:mb-0" />
            <h1 className="text-[clamp(34px,4.4vw,48px)] leading-[1.02]">{chapter.title}</h1>
            {consentPending ? (
              <ConsentPending what="you can watch the free clips, but nothing you watch is saved" />
            ) : null}
            {player}
            <LockedList clips={clips} current={current?.id ?? null} path={path} />
            <p className="text-[15px] leading-normal text-ink/85">
              The first clip of every chapter is free, and so are the flash cards of each subject&apos;s first chapter.
            </p>
            {chapter.free_cards ? <Practice chapter={chapter} path={path} /> : null}
          </div>
          <RedeemCard subject={subject.name} consentPending={consentPending} />
        </div>
      </Sheet>
    );
  }

  return (
    <Sheet
      margin={`Ch.${chapter.number}`}
      marks={<Marks items={[{ value: marks, label: `Board marks · ${chapter.frequency ?? 0} past Qs` }]} />}
      className="course-sheet"
      bodyClassName="nav:pt-7 nav:pb-16"
    >
      <div className="flex flex-col gap-3 [&_p]:m-0">
        <Breadcrumb trail={trail} className="[&_ol]:mb-0" />
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <h1 className="text-[clamp(34px,4.6vw,52px)] leading-none">{chapter.title}</h1>
          <p className="text-[15px] text-muted-foreground">
            {plural(chapter.clips, "clip")} · {chapter.minutes} min · {watched} of {chapter.clips} watched
          </p>
        </div>
        {consentPending ? <ConsentPending what="you can watch here, but nothing you watch or answer is saved" /> : null}
      </div>
      <div className="mt-7 grid items-start gap-10 max-nav:mt-6 max-nav:gap-6 nav:grid-cols-[340px_minmax(0,1fr)]">
        {player ?? <p className="m-0 text-muted-foreground">No clip of this chapter is ready yet.</p>}
        <div className="flex min-w-0 flex-col gap-[22px]">
          <ClipList clips={clips} current={current?.id ?? null} path={path} />
          {clip && !(clip instanceof ApiError) ? <ClipNotes clip={clip} /> : null}
          <Practice chapter={chapter} path={path} />
        </div>
      </div>
    </Sheet>
  );
}
