// Markdown with $…$ maths, rendered on the server (react-markdown + remark-math + rehype-katex): the page arrives with
// its formulas already drawn, so no maths script runs on the phone. KaTeX's HTML only (output "html"): its MathML
// copy doubled each formula in the page and in the RSC payload (Lighthouse review L4), and the browsers' own MathML
// reads worse than KaTeX's HTML in both Chrome and Safari (vector arrows off their letters, "sin θ" run together, no
// line breaks in a long inline formula); screen readers then read the formula's characters in order, not its MathML
// structure. GitHub tables for the marking steps; raw HTML
// (comments included) is dropped, as on the Django site. Each text is rendered once per server process (the Django
// site keeps an lru_cache of its rendering the same way): a paper's KaTeX work is not repeated for every visitor.
import Markdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import rehypeExamleaf from "./rehype-examleaf";

const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins = [
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

export function MarkdownInline({ children }: { children: string }) {
  return <>{render(children, true)}</>;
}
