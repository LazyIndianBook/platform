"use client";

// HTML the API rendered from Markdown (raw HTML off, so it is safe to insert) whose $…$ maths it leaves for KaTeX:
// a quiz answer's explanation, which exists in the page only once the server has checked the answer, so it cannot be
// drawn on the server like the questions. KaTeX's script loads only for an explanation that has maths.
import { useEffect, useState } from "react";

const MATH = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

/** The maths as typed: Django escaped it for HTML (quotes too). */
const plain = (html: string) => new DOMParser().parseFromString(html, "text/html").documentElement.textContent ?? "";

/** Plain text from the API (a right answer) as HTML, for MathHtml. */
export const escapeHtml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function MathHtml({ html, className, inline = false }: { html: string; className?: string; inline?: boolean }) {
  const [drawn, setDrawn] = useState<{ from: string; html: string } | null>(null);
  useEffect(() => {
    if (!html.match(MATH)) return;
    let gone = false;
    import("katex").then(({ default: katex }) => {
      if (gone) return;
      const out = html.replace(MATH, (_, block: string | undefined, inline: string | undefined) =>
        katex.renderToString(plain(block ?? inline ?? ""), { displayMode: block !== undefined, throwOnError: false }),
      );
      setDrawn({ from: html, html: out });
    });
    return () => {
      gone = true;
    };
  }, [html]);
  const Tag = inline ? "span" : "div";
  return <Tag className={className} dangerouslySetInnerHTML={{ __html: drawn?.from === html ? drawn.html : html }} />;
}
