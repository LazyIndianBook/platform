// Markdown with $…$ maths, rendered on the server (react-markdown + remark-math + rehype-katex): the page arrives with
// its formulas already drawn, so no maths script runs on the phone. KaTeX's HTML only (output "html"): its MathML
// copy doubled each formula in the page and in the RSC payload (Lighthouse review L4), and the browsers' own MathML
// reads worse than KaTeX's HTML in both Chrome and Safari (vector arrows off their letters, "sin θ" run together, no
// line breaks in a long inline formula); rehype-math-speech.ts gives each formula words for screen readers instead.
// GitHub tables for the marking steps; raw HTML
// (comments included) is dropped, as on the Django site. A text is rendered once per server process while it is in
// use (the Django site keeps an lru_cache of its rendering the same way): a paper's KaTeX work (about 176 ms for a
// whole paper's solutions) is not repeated for every visitor.
import Markdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import rehypeExamleaf from "./rehype-examleaf";
import rehypeMathSpeech from "./rehype-math-speech";

const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins = [
  rehypeMathSpeech,
  [rehypeKatex, { throwOnError: false, strict: "ignore", output: "html" }],
  rehypeExamleaf,
] as const;
const INLINE: Components = { p: ({ children }) => <>{children}</> };

// ponytail: a per-process LRU bounded by the texts' length, because the rendered tree is what costs: on the test
// papers' solutions about 375 bytes of heap per character of Markdown (220 KB of text kept 80 MB, 129 KB a text), so
// the old limit of 4000 texts was about 500 MB, more than the pod's whole 512 MiB. 160 000 characters is about 60 MB,
// ten papers' solutions; raise it with the pod's memory and NODE_OPTIONS, or share a cache once several servers run.
export const CACHE_CHARS = 160_000;
const cache = new Map<string, React.ReactNode>();
let cachedChars = 0;

function render(source: string, inline: boolean): React.ReactNode {
  const key = `${inline ? "i" : "b"}:${source}`;
  const hit = cache.get(key);
  if (hit !== undefined) {
    cache.delete(key); // used again: the most recent, the last to go
    cache.set(key, hit);
    return hit;
  }
  // inline: one line ("1. Answer any eight …" is a heading, not a list)
  const text = inline ? source.replace(/^(\s*\d+)\./, "$1\\.") : source;
  const node = Markdown({
    children: text,
    remarkPlugins,
    rehypePlugins: rehypePlugins as never,
    skipHtml: true,
    components: inline ? INLINE : undefined,
  });
  cache.set(key, node);
  cachedChars += key.length;
  for (const old of cache.keys()) {
    if (cachedChars <= CACHE_CHARS) break;
    cache.delete(old); // the least recently used first (a text over the whole budget goes too, rendered all the same)
    cachedChars -= old.length;
  }
  return node;
}

export function MarkdownBlock({ children }: { children: string }) {
  return <>{render(children, false)}</>;
}

/** A group heading as the papers print it, "1. Answer any eight … : `1×8=8`", in its three places on the page: the
 *  number for the margin, the words, the marks for the marks column. Either end may be missing. */
export function splitGroup(label: string): { number: string | null; text: string; marks: string | null } {
  const [, number, text, marks] = /^\s*(?:(\d+)\.\s+)?([\s\S]*?)\s*(?:`([^`]+)`)?\s*$/.exec(label)!;
  return { number: number ? `${number}.` : null, text, marks: marks ?? null };
}

/** The marking steps of a solution: the rows of its marking tables (last column "Marks"), the Total row left out. */
export function stepCount(markdown: string): number {
  const lines = markdown.split("\n").map((line) => line.trim());
  let count = 0;
  lines.forEach((line, index) => {
    if (!/^\|[\s:|-]+\|$/.test(line) || !/\|\s*\**marks\**\s*\|$/i.test(lines[index - 1] ?? "")) return;
    for (let row = index + 1; lines[row]?.startsWith("|"); row++)
      if (!/^\|\s*\**total\**\s*\|/i.test(lines[row])) count++;
  });
  return count;
}

export function MarkdownInline({ children }: { children: string }) {
  return <>{render(children, true)}</>;
}
