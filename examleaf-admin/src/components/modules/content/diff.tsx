// One field's change, as the API diffs it (difflib, line by line): the lines kept, removed and added, each with its
// sign and, for a screen reader, its word; never the tint alone. A short value reads as "before → after".
import type { ContentChange } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const words = copy.content.reviews;
const SIGN = { equal: " ", delete: "−", insert: "+" } as const;

const short = (value: unknown) =>
  value === null || value === undefined || value === "" ? copy.common.none : typeof value === "string" ? value : JSON.stringify(value);

export function Diff({ change, title }: { change: ContentChange; title?: string }) {
  const name = title ?? labelOf(words.fieldNames, change.field.replace(/^draft\./, ""));
  const multiline = change.lines.length > 2 || change.lines.some((line) => line.text.length > 60);
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-1.5">
      <figcaption className="text-sm font-semibold">{name}</figcaption>
      {multiline ? (
        <ol className="content-diff">
          {change.lines.map((line, index) => (
            <li key={index} data-op={line.op}>
              <span aria-hidden="true">{SIGN[line.op]}</span>
              <span>
                {line.op === "equal" ? null : <span className="sr-only">{line.op === "insert" ? words.added : words.removed}: </span>}
                {line.text || " "}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-0 text-[15px] break-words">
          <span className="text-muted-foreground line-through">{short(change.before)}</span>
          <span aria-hidden="true"> → </span>
          <span className="sr-only"> {words.after}: </span>
          <span className="font-semibold">{short(change.after)}</span>
        </p>
      )}
    </figure>
  );
}
