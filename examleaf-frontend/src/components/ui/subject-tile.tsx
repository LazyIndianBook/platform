// .tile: a subject's cover colours, 2 px ink outline, 4 px hard shadow; :active drops it into its shadow (the
// sticker press, globals.css). Its view-transition name pairs it with the Book page's cover.
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import type { SubjectKey } from "@/lib/site";

import { CoverPicture } from "./cover";

type SubjectTileProps = {
  subject: SubjectKey;
  name: string;
  href: string;
  papers?: number;
  marks?: number;
  time?: string;
  cover?: string | null;
};

function SubjectTile({ subject, name, href, papers = 30, marks, time, cover }: SubjectTileProps) {
  return (
    <Link href={href} className={`tile subject-${subject}`}>
      <span className="inline-flex h-6 items-center self-start rounded-pill bg-(--pill) px-2.5 font-head text-xs leading-none font-bold text-(--base)">
        {papers} papers
      </span>
      <span className="font-head text-[28px] leading-[1.15] font-extrabold">{name}</span>
      <span className="text-[15px] leading-normal font-semibold text-(--pill)">
        10 Easy · 10 Medium · 10 Hard
        {marks ? (
          <>
            <br />
            {marks} marks · {time}
          </>
        ) : null}
      </span>
      <span className="mt-auto max-w-[58%] text-base leading-snug font-semibold">
        Open the papers <ArrowRight aria-hidden="true" className="ml-1 inline size-5 align-[-4px]" />
      </span>
      {cover ? (
        <CoverPicture
          src={cover}
          alt=""
          sizes="112px"
          className="absolute -right-3.5 -bottom-[34px] w-28 rotate-8 rounded-cover shadow-cover"
        />
      ) : null}
    </Link>
  );
}

export { SubjectTile };
