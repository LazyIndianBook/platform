"""The structural check of what a solution or a question may hold (content.latex): unbalanced and dangerous input
refused with its line, every solution and question of the test papers accepted as written."""

import pytest

from . import latex, papers_parser
from .imports import FIXTURES


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("The current is $I = 0.5 A", "Line 1: $ opens maths and nothing closes it."),
        ("$$\nx = 1", "Line 1: $$ opens maths and nothing closes it."),
        ("a \\(x\n\\) b", "Line 1: \\( opens maths that does not close on its line."),
        ("x\\]", "Line 1: \\] closes maths that was never opened."),
        ("$\\frac{1}{2$", "Line 1: 1 { is never closed with }."),
        ("$x}$", "Line 1: a } closes a brace that was never opened."),
        ("$\\begin{matrix}1\\end{pmatrix}$", "Line 1: \\end{pmatrix} closes \\begin{matrix}."),
        ("$$\\begin{cases}x\n$$", "Line 1: \\begin{cases} has no \\end{cases}."),
        ("$\\href{https://example.com}{see}$", "Line 1: \\href is not allowed (links and pictures go in the"),
        ("\\includegraphics{a.png}", "Line 1: \\includegraphics is not allowed"),
        ("$\\htmlClass{x}{y}$", "Line 1: \\htmlClass is not allowed"),
        ("<script>alert(1)</script>", "Line 1: raw HTML (<script>) is not allowed: write Markdown."),
        ("one\n<img src=x onerror=alert(1)>", "Line 2: raw HTML (<img>) is not allowed"),
        ("![](circuit.png)", 'Line 1: a picture needs its alt text (what it shows), or the title "decorative"'),
        ("![A circuit](javascript:alert(1))", "Line 1: a picture comes from an https:// address or the site itself."),
        ("![A circuit](http://example.com/c.png)", "Line 1: a picture comes from an https:// address"),
    ],
)
def test_unbalanced_and_dangerous_input_is_refused_with_its_line(text, problem):
    assert any(found.startswith(problem) for found in latex.problems(text)), latex.problems(text)


@pytest.mark.parametrize(
    "text",
    [
        "| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |\n\n**Final answer:** 0.5 A",
        "$$\\begin{pmatrix}1 & 2\\\\3 & 4\\end{pmatrix}$$",
        "Rs \\$5, `$PATH`, a < b and $x<y$, <!-- the editor's note -->",
        '![](rule.png "decorative") and ![The circuit](https://media.examleaf.in/c.png)',
        "\\[x^2\\] and \\(y\\)",
    ],
)
def test_good_input_passes(text):
    assert latex.problems(text) == []


def test_every_solution_and_question_of_the_test_papers_passes():
    checked = 0
    for path in sorted((FIXTURES / "production").glob("*/papers_md/*.md")):
        if path.name.endswith("-solutions.md"):
            texts = ["\n".join(item["lines"]).strip() for item in papers_parser.parse_solutions(str(path))]
        else:
            body = papers_parser.parse_paper(str(path))["body"]
            texts = [part for block in body for part in [block.get("text", ""), *block.get("options", [])]]
        for text in texts:
            assert latex.problems(text) == [], (path.name, text[:80])
            checked += 1
    assert checked > 1200
