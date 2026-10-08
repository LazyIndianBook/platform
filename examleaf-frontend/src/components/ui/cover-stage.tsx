// .stage: the four covers fanned (−8°, −3°, 3°, 8°); each is the link to its book and lifts 14 px with its spine
// catching the light on hover, keyboard focus or tap (motion.md, a; globals.css). Nothing moves on load; the first
// cover is the page's priority image.
import Link from "next/link";

import { CoverPicture } from "./cover";

type StageBook = { href: string; cover: string; title: string };

function CoverStage({ books }: { books: StageBook[] }) {
  if (!books.length) return null;
  return (
    <div className="stage">
      {books.slice(0, 4).map((book, index) => (
        <Link key={book.href} href={book.href} className="cover stage-cover" aria-label={book.title}>
          <CoverPicture
            src={book.cover}
            alt={`${book.title}, cover`}
            sizes="(min-width: 900px) 172px, 104px"
            priority={index === 0}
          />
        </Link>
      ))}
    </div>
  );
}

export { CoverStage, type StageBook };
