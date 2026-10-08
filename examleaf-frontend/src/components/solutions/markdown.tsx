// Markdown with $…$ maths, rendered on the server (react-markdown + remark-math + rehype-katex): the page arrives with
// its formulas already drawn, so no maths script runs on the phone. KaTeX's HTML only (output "html"): its MathML
// copy doubled each formula in the page and in the RSC payload (Lighthouse review L4), and the browsers' own MathML
// reads worse than KaTeX's HTML in both Chrome and Safari (vector arrows off their letters, "sin θ" run together, no
// line breaks in a long inline formula); rehype-math-speech.ts gives each formula words for screen readers instead.
// GitHub tables for the marking steps; raw HTML
// (comments included) is dropped, as on the Django site. Each text is rendered once per server process (the Django
// site keeps an lru_cache of its rendering the same way): a paper's KaTeX work is not repeated for every visitor.
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

// ponytail: a bounded per-process cache (oldest entry dropped first); a shared cache only if several servers run
const CACHE_LIMIT = 4000;
const cache = new Map<string, React.ReactNode>();

function render(source: string, inline: boolean): React.ReactNode {
  const key = `${inline ? "i" : "b"}:${source}`;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  // inline: one line ("1. Answer any eight …" is a heading, not a list)
  const text = inline ? source.replace(/^(\s*\d+)\./, "$1\\.") : source;
  const node = Markdown({
    children: text,
    remarkPlugins,
    rehypePlugins: rehypePlugins as never,
    skipHtml: true,
    components: inline ? INLINE : undefined,
  });
  if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value!);
  cache.set(key, node);
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
