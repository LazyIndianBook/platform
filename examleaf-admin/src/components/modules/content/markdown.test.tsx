// The editor's preview draws a solution as the site does (the marking table, maths through KaTeX, raw HTML as text)
// and shows bad LaTeX in red where it is; before a save, every formula KaTeX refuses is named with its line.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, mathProblems } from "./markdown";

const SOLUTION = [
  "| Step | Marks |",
  "|---|---|",
  "| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |",
  "| $I = 0.5$ A | 1 |",
  "",
  "**Final answer:** 0.5 A",
  "",
  "> *Diagram expected:* the circuit",
].join("\n");

describe("Markdown", () => {
  it("draws the marking table, the maths and the final answer", () => {
    const { container } = render(<Markdown source={SOLUTION} />);
    const table = screen.getByRole("table");
    expect(table).toHaveClass("steps");
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Step", "Marks"]);
    expect(container.querySelectorAll(".katex")).toHaveLength(2);
    expect(container.querySelector(".katex-error")).toBeNull();
    expect(container.querySelector("p.final strong")).toHaveTextContent("Final answer:");
    expect(container.querySelector("blockquote em")).toHaveTextContent("Diagram expected:");
  });

  it("shows bad LaTeX in red where it is, its message escaped, and never runs \\href", () => {
    const { container } = render(<Markdown source={"Bad: $\\frac{1}{<b>x</b>$ and $\\href{javascript:alert(1)}{y}$"} />);
    const errors = container.querySelectorAll(".katex-error");
    expect(errors.length).toBeGreaterThan(0);
    expect(container.querySelector("b")).toBeNull(); // the source's HTML stays text inside the error
    expect(container.querySelector("a")).toBeNull(); // trust off: no link from the maths
  });

  it("keeps raw HTML as text, drops comments, and follows only safe links and pictures", () => {
    const { container } = render(
      <Markdown
        source={'<script>alert(1)</script> <!-- note --> [ok](https://examleaf.in/) [no](javascript:x) ![A circuit](https://media.examleaf.in/c.png) ![](rule.png "decorative")'}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container).toHaveTextContent("<script>alert(1)</script>");
    expect(container).not.toHaveTextContent("note");
    expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["https://examleaf.in/"]);
    expect(screen.getByRole("img", { name: "A circuit" })).toHaveAttribute("src", "https://media.examleaf.in/c.png");
    expect(container.querySelector('img[src="rule.png"]')).toHaveAttribute("alt", "");
  });

  it("draws a block of maths, lists, headings and escaped dollars", () => {
    const { container } = render(<Markdown source={"## Part A\n\n$$\nx^2\n$$\n\n- one\n- two\n\nRs \\$5"} />);
    expect(screen.getByRole("heading", { level: 4 })).toHaveTextContent("Part A");
    expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(container).toHaveTextContent("Rs $5");
  });
});

describe("mathProblems", () => {
  it("names each formula KaTeX refuses, with its line", () => {
    const problems = mathProblems("Fine: $x^2$\n\nBroken: $\\frac{1}{2$\n`$not maths$`\n$\\undefinedcommand$");
    expect(problems.map((problem) => problem.line)).toEqual([3, 5]);
    expect(problems[0].message).toMatch(/expected '}'/);
    expect(problems[1].message).toMatch(/Undefined control sequence/);
  });

  it("finds none in a good solution", () => {
    expect(mathProblems(SOLUTION)).toEqual([]);
  });
});
