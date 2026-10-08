// The subject row, Direction A (Components board, 07: "SUBJECT ROW · COVER"): the cover (56 × 80, radius 3), the
// subject in the serif, the book's figures in 14 px muted ("30 papers · 70 marks · 3 hours", from the API: no tier
// split is claimed), one link "Open the book" (words for screen readers only on a phone). The whole row is the link:
// paper 2 on hover, a 1 px press. Same props (className added); still morphs into the Book page's cover
// (Morph "book-<subject>").
import { cn } from "cn";
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
  className?: string;
};

function SubjectTile({ subject, name, href, papers = 30, marks, time, cover, className }: SubjectTileProps) {
  const facts = [`${papers} papers`, marks ? `${marks} marks` : "", time ?? ""].filter(Boolean).join(" · ");
  return (
    <Link href={href} className={cn(`tile subject-${subject}`, className)}>
      {cover ? (
        <Morph name={`book-${subject}`}>
          <CoverPicture
            src={cover}
            alt=""
            sizes="56px"
            className="w-14 rounded-[3px] shadow-[0_6px_12px_-6px_rgba(0,0,0,0.5)]"
          />
        </Morph>
      ) : (
        <span aria-hidden="true" className="block aspect-[480/678] w-14 rounded-[3px] bg-(--base)" />
      )}
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-head text-2xl leading-[1.1] font-semibold">{name}</span>
        <span className="text-sm leading-snug text-muted-foreground">{facts}</span>
      </span>
      <span className="inline-flex items-center gap-1.5 font-bold whitespace-nowrap text-primary max-nav:sr-only">
        Open the book <ArrowRight aria-hidden="true" className="size-5" />
      </span>
    </Link>
  );
}

export { SubjectTile };
