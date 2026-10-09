// A solution or a question as the public site draws it, for the editor's preview and the review's: Markdown with
// $…$ and $$…$$ maths through KaTeX with the site's options (examleaf-frontend/src/components/solutions/markdown.tsx:
// output "html", strict "ignore"; trust off, so \href, \url and \includegraphics never run; throwOnError off, so bad
// LaTeX shows in red where it is, KaTeX's message escaped in its title). The site's Markdown is react-markdown with
// GitHub tables; this draws the part of it the books use (paragraphs, headings, emphasis, code, lists, quotes, the
// marking tables, links and pictures), raw HTML never (as text, as the site drops it), comments dropped. Before a save
// `mathProblems` parses every formula with throwOnError on: what KaTeX refuses is not sent (the backend's own
// structural check, content/latex.py, decides again).
import "katex/dist/katex.min.css";
import "./content.css";

import { cn } from "cn";
import katex from "katex";
import { Fragment, type ReactNode } from "react";

const OPTIONS = { output: "html", strict: "ignore", trust: false } as const;
const COMMENT = /<!--[\s\S]*?-->/g;

/** A formula drawn by KaTeX: the site's options; an error in red with its message (escaped by KaTeX), never thrown. */
export function mathHtml(tex: string, display: boolean): string {
  return katex.renderToString(tex, { ...OPTIONS, displayMode: display, throwOnError: false });
}

export type MathProblem = { line: number; formula: string; message: string };

/** Every formula of a text that KaTeX refuses with throwOnError on, with its line: none, and it may be sent. */
export function mathProblems(source: string): MathProblem[] {
  const text = source.replace(COMMENT, (comment) => comment.replace(/[^\n]/g, " "));
  const found: MathProblem[] = [];
  for (const { tex, display, at } of formulas(stripCode(text))) {
    try {
      katex.renderToString(tex, { ...OPTIONS, displayMode: display, throwOnError: true });
    } catch (error) {
      const message = error instanceof Error ? error.message.replace(/^KaTeX parse error: /, "") : String(error);
      found.push({ line: text.slice(0, at).split("\n").length, formula: tex, message });
    }
  }
  return found;
}

/** Code spans and fences as spaces (positions kept): the dollars in them are no maths. */
function stripCode(text: string): string {
  const blank = (part: string) => part.replace(/[^\n]/g, " ");
  return text.replace(/^(```|~~~)[\s\S]*?^\1[ \t]*$/gm, blank).replace(/(`+)(?!`)[\s\S]*?[^`]\1(?!`)/g, blank);
}

/** The formulas of a text as the site's remark-math finds them: $$…$$ (display) and $…$ on one line. */
function formulas(text: string): { tex: string; display: boolean; at: number }[] {
  const found: { tex: string; display: boolean; at: number }[] = [];
  const pattern = /\\[\\$]|\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;
  for (const match of text.matchAll(pattern)) {
    if (match[0].startsWith("\\")) continue; // \$ and \\: no maths
    found.push({ tex: match[1] ?? match[2], display: match[1] !== undefined, at: match.index ?? 0 });
  }
  return found;
}

// ---- Inline: code, maths, pictures, links, emphasis, escapes, line breaks ----

const INLINE = new RegExp(
  [
    "\\\\([!-/:-@[-`{-~])", // an escape
    "(`+)([\\s\\S]*?[^`])\\2(?!`)", // code
    "\\$\\$([\\s\\S]+?)\\$\\$", // maths in its own block
    "\\$([^$\\n]+?)\\$", // maths in the line
    '!\\[([^\\]]*)\\]\\(\\s*<?([^)\\s>]*)>?(?:\\s+"([^"]*)")?\\s*\\)', // a picture
    "\\[([^\\]]+)\\]\\(\\s*<?([^)\\s>]+)>?(?:\\s+\"[^\"]*\")?\\s*\\)", // a link
    "\\*\\*([\\s\\S]+?)\\*\\*|__([\\s\\S]+?)__", // strong
    "\\*([^*\\n]+?)\\*|(?<![A-Za-z0-9])_([^_\\n]+?)_(?![A-Za-z0-9])", // emphasis
    "(?: {2,}|\\\\)\\n", // a hard break
  ].join("|"),
  "g",
);

/** A link or a picture's address the site would follow: https, mail, or a path of the site. */
function safeUrl(url: string, picture = false): string | null {
  if (/^https:\/\//i.test(url) || (!picture && /^mailto:/i.test(url))) return url;
  return /^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith("//") || !url ? null : url;
}

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(INLINE)) {
    const at = match.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    last = at + match[0].length;
    const k = `${key}-${n++}`;
    const [, escaped, , code, block, line, alt, src, title, linkText, href, strong, strong2, em, em2] = match;
    if (escaped !== undefined) out.push(escaped);
    else if (code !== undefined) out.push(<code key={k}>{code.trim()}</code>);
    else if (block !== undefined || line !== undefined)
      out.push(
        <span
          key={k}
          className={block !== undefined ? "block overflow-x-auto" : undefined}
          dangerouslySetInnerHTML={{ __html: mathHtml(block ?? line, block !== undefined) }}
        />,
      );
    else if (src !== undefined) {
      const url = safeUrl(src, true);
      // eslint-disable-next-line @next/next/no-img-element
      if (url) out.push(<img key={k} src={url} alt={title?.toLowerCase() === "decorative" ? "" : alt} />);
      else out.push(alt);
    } else if (href !== undefined) {
      const url = safeUrl(href);
      out.push(
        url ? (
          <a key={k} href={url} rel="noopener noreferrer">
            {inline(linkText, k)}
          </a>
        ) : (
          <Fragment key={k}>{inline(linkText, k)}</Fragment>
        ),
      );
    } else if (strong !== undefined || strong2 !== undefined)
      out.push(<strong key={k}>{inline(strong ?? strong2, k)}</strong>);
    else if (em !== undefined || em2 !== undefined) out.push(<em key={k}>{inline(em ?? em2, k)}</em>);
    else out.push(<br key={k} />);
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// ---- Blocks ----

const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const LIST_ITEM = /^\s{0,3}([-*+]|\d{1,9}[.)])\s+(.*)$/;
const STARTS = [/^\s{0,3}#{1,6}\s/, /^\s{0,3}>/, /^\s{0,3}(```|~~~)/, /^\s*\$\$/, LIST_ITEM, /^\s{0,3}([-*_])(\s*\1){2,}\s*$/];

/** A table row's cells: split at the pipes not escaped (as GitHub's tables do, inside maths too). */
function cells(row: string): string[] {
  const inner = row.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "");
  return inner.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

function blocks(lines: string[], key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let i = 0;
  const next = () => `${key}-${out.length}`;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const fence = /^\s{0,3}(```|~~~)/.exec(line);
    if (fence) {
      const body: string[] = [];
      for (i += 1; i < lines.length && !lines[i].trim().startsWith(fence[1]); i += 1) body.push(lines[i]);
      i += 1;
      out.push(
        <pre key={next()}>
          <code>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    if (/^\s*\$\$/.test(line)) {
      // a block of maths: to the line that closes it (an unclosed one runs to the end, as on the site)
      const body: string[] = [];
      let rest = line.trim().slice(2);
      for (i += 1; ; i += 1) {
        const end = rest.indexOf("$$");
        body.push(end >= 0 ? rest.slice(0, end) : rest);
        if (end >= 0 || i >= lines.length) break;
        rest = lines[i];
      }
      out.push(
        <div
          key={next()}
          className="overflow-x-auto"
          dangerouslySetInnerHTML={{ __html: mathHtml(body.join("\n"), true) }}
        />,
      );
      continue;
    }
    const heading = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (heading) {
      const Tag = `h${Math.min(6, heading[1].length + 2)}` as "h3";
      out.push(<Tag key={next()}>{inline(heading[2], next())}</Tag>);
      i += 1;
      continue;
    }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
      out.push(<hr key={next()} />);
      i += 1;
      continue;
    }
    if (/^\s{0,3}>/.test(line)) {
      const quoted: string[] = [];
      for (; i < lines.length && /^\s{0,3}>/.test(lines[i]); i += 1) quoted.push(lines[i].replace(/^\s{0,3}>\s?/, ""));
      out.push(<blockquote key={next()}>{blocks(quoted, next())}</blockquote>);
      continue;
    }
    if (line.includes("|") && TABLE_RULE.test(lines[i + 1] ?? "")) {
      const head = cells(line);
      const rows: string[][] = [];
      for (i += 2; i < lines.length && lines[i].trim() && lines[i].includes("|"); i += 1) rows.push(cells(lines[i]));
      const k = next();
      const steps = head.at(-1)?.replace(/\*/g, "").trim().toLowerCase() === "marks";
      out.push(
        <div key={k} className="table-scroll">
          <table className={steps ? "steps" : undefined}>
            <thead>
              <tr>
                {head.map((cell, c) => (
                  <th key={c} scope="col">
                    {inline(cell, `${k}-h${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>
                  {head.map((_, c) => (
                    <td key={c}>{inline(row[c] ?? "", `${k}-${r}-${c}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const item = LIST_ITEM.exec(line);
    if (item) {
      const ordered = /\d/.test(item[1]);
      const items: string[] = [];
      for (; i < lines.length; i += 1) {
        const each = LIST_ITEM.exec(lines[i]);
        if (each && /\d/.test(each[1]) === ordered) items.push(each[2]);
        else if (lines[i].trim() && /^\s+/.test(lines[i]) && items.length) items[items.length - 1] += `\n${lines[i]}`;
        else break;
      }
      const List = ordered ? "ol" : "ul";
      const k = next();
      out.push(
        <List key={k}>
          {items.map((text, n) => (
            <li key={n}>{inline(text.trim(), `${k}-${n}`)}</li>
          ))}
        </List>,
      );
      continue;
    }
    const paragraph: string[] = [];
    for (; i < lines.length && lines[i].trim(); i += 1) {
      const tableNext = lines[i].includes("|") && TABLE_RULE.test(lines[i + 1] ?? "");
      if (paragraph.length && (tableNext || STARTS.some((start) => start.test(lines[i])))) break;
      paragraph.push(lines[i]);
    }
    const k = next();
    const text = paragraph.join("\n");
    out.push(
      <p key={k} className={/^\*\*Final answer:\*\*/.test(text) ? "final" : undefined}>
        {inline(text, k)}
      </p>,
    );
  }
  return out;
}

/** Markdown with maths as React elements, the site's way (raw HTML stays text, comments go). */
export function renderMarkdown(source: string): ReactNode[] {
  return blocks(source.replace(/\r\n?/g, "\n").replace(COMMENT, "").split("\n"), "md");
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  return <div className={cn("content-markdown", className)}>{renderMarkdown(source)}</div>;
}
