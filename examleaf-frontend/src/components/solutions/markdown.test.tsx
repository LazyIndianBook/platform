// The solutions' Markdown as the Django site renders it: marking tables, final answers, diagrams, maths drawn by
// KaTeX on the server, no raw HTML.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { isMinor } from "@/lib/dates";

import { MarkdownBlock, MarkdownInline, splitGroup, stepCount } from "./markdown";

const SOLUTION = [
  "| Step | Marks |",
  "|---|---|",
  "| Formula: $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |",
  "| **Total** | **1** |",
  "",
  "**Final answer:** 0.5 A",
  "",
  "*Also accepted:* $n_e \\gg n_h$",
  "",
  "> *Diagram expected:* the circuit.",
  "",
  "<!-- a note for the editors --><script>alert(1)</script>",
].join("\n");

describe("MarkdownBlock", () => {
  it("styles the solution lines and draws the maths", () => {
    const { container } = render(<MarkdownBlock>{SOLUTION}</MarkdownBlock>);
    expect(container.querySelector(".table-scroll > table.steps")).not.toBeNull();
    expect(container.querySelector("p.final")).toHaveTextContent("Final answer: 0.5 A");
    expect(container.querySelector("p.also")).not.toBeNull();
    expect(container.querySelector("blockquote.diagram")).toHaveTextContent("Diagram expected: the circuit.");
    expect(container.querySelectorAll(".katex").length).toBe(2);
    // KaTeX's HTML only: no MathML copy of each formula (Lighthouse review L4)
    expect(container.querySelectorAll(".katex-html").length).toBe(2);
    expect(container.querySelector("math, .katex-mathml")).toBeNull();
    // ... and words for screen readers on each formula, the drawing hidden from them
    const formula = container.querySelector('[role="img"][aria-label]');
    expect(formula?.getAttribute("aria-label")).toMatch(/\w/);
    expect(formula?.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(formula?.querySelector(".katex-html")).not.toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).not.toContain("alert(1)");
    expect(container.innerHTML).not.toContain("editors");
  });

  it("keeps a group heading on one line, its marks as code", () => {
    const { container } = render(<MarkdownInline>{"1. Answer any eight questions : `1×8=8`"}</MarkdownInline>);
    expect(container.querySelector("ol, p")).toBeNull();
    expect(container.querySelector("code")).toHaveTextContent("1×8=8");
  });
});

describe("the solutions page's reading of the text", () => {
  it("splits a group heading into its margin number, words and marks", () => {
    expect(splitGroup("1. Answer any eight questions from the following as directed : `1×8=8`")).toEqual({
      number: "1.",
      text: "Answer any eight questions from the following as directed :",
      marks: "1×8=8",
    });
    expect(splitGroup("Answer the following questions :")).toEqual({
      number: null,
      text: "Answer the following questions :",
      marks: null,
    });
  });

  it("counts a solution's marking steps, without its Total row", () => {
    expect(stepCount(SOLUTION)).toBe(1);
    expect(stepCount("| Step | **Marks** |\n| --- | :---: |\n| a | 1 |\n| b | 1 |\n| **Total** | **2** |")).toBe(2);
    expect(stepCount("**Ans.** square *(1)*")).toBe(0);
    expect(stepCount("| Item | Value |\n|---|---|\n| a | 1 |")).toBe(0); // a table that is not a marking table
  });
});

describe("isMinor", () => {
  it("is under 18 on the day", () => {
    const today = new Date(2026, 9, 8);
    expect(isMinor("2008-10-08", today)).toBe(false);
    expect(isMinor("2008-10-09", today)).toBe(true);
    expect(isMinor("", today)).toBe(false);
  });
});
