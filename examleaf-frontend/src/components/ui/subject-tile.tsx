// The subject row (was the sticker tile), Direction A: cover, the subject in serif, the book's figures in the mono
// voice, one link. Same props; still morphs into the Book page's cover (Morph "book-<subject>").
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import type { SubjectKey } from "@/lib/site";

import { CoverPicture } from "./cover";
import { Morph } from "./morph";

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
      {cover ? (
        <Morph name={`book-${subject}`}>
          <CoverPicture src={cover} alt="" sizes="64px" className="w-16 rounded-cover shadow-cover" />
        </Morph>
      ) : (
        <span aria-hidden="true" className="block aspect-[480/678] w-16 rounded-cover bg-(--base)" />
      )}
      <span className="flex min-w-0 flex-col gap-1">
        <span className="font-head text-[28px] leading-[1.1] font-semibold">{name}</span>
        <span className="font-mono text-[13px] leading-snug text-muted-foreground">
          {papers} papers · 10 Easy · 10 Medium · 10 Hard{marks ? ` · ${marks} marks · ${time}` : ""}
        </span>
      </span>
      <span className="inline-flex items-center gap-1.5 font-bold whitespace-nowrap text-primary max-nav:sr-only">
        Open the book <ArrowRight aria-hidden="true" className="size-5" />
      </span>
    </Link>
  );
}

export { SubjectTile };
