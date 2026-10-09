"""What a saved solution or question may hold (plan 5.10, research-lms-crm-cms.md 2.1): a structural check of its
Markdown and LaTeX, run on every save from the panel (the console also parses each formula with KaTeX before it
sends). Maths opens and closes on the line it starts ($…$, \\(…\\)) or in a block ($$…$$, \\[…\\]); braces balance
and every \\begin{…} has its \\end{…} in the same formula; no \\href, \\url, \\includegraphics or KaTeX's \\html…
commands (the site renders with trust off: they would show as errors); no raw HTML (both renderers drop it; the
books' <!-- comments --> stay allowed); a picture has its alt text, or the title "decorative", and comes from an
https address or the site. `problems(text)` answers the problems in plain sentences, each with its line, or none."""

import re

COMMENT = re.compile(r"<!--.*?-->", re.S)
FENCED = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.S | re.M)
CODE_SPAN = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")
HTML_TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)(?:\s[^<>]*)?/?>")
IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+[\"']([^\"']*)[\"'])?\s*\)")
FORBIDDEN = re.compile(r"\\(href|url|includegraphics|htmlClass|htmlId|htmlStyle|htmlData)(?![A-Za-z])")
ENVIRONMENT = re.compile(r"\\(begin|end)\s*\{([^{}]*)\}")
OPENERS = {"$": "$", "$$": "$$", "\\(": "\\)", "\\[": "\\]"}
BLOCKS = {"$$", "\\["}  # may run over several lines; the others close on the line they open


def blank(text, start, end):
    """`text` with [start, end) as spaces (its newlines kept): positions and line numbers stay."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def blanked(pattern, text):
    for match in reversed(list(pattern.finditer(text))):
        text = blank(text, match.start(), match.end())
    return text


def line_of(text, position):
    return text.count("\n", 0, position) + 1


def tokens(text):
    """(position, token) of the maths delimiters: $, $$, \\( \\) \\[ \\]; an escaped \\$ and \\\\ are none."""
    i, end = 0, len(text)
    while i < end:
        if text[i] == "\\" and i + 1 < end:
            if text[i : i + 2] in ("\\(", "\\)", "\\[", "\\]"):
                yield i, text[i : i + 2]
            i += 2  # \$, \\ and \{ are literals; a command's letters follow as text
        elif text[i] == "$":
            token = "$$" if text.startswith("$$", i) else "$"
            yield i, token
            i += len(token)
        else:
            i += 1


def formulas(text, found):
    """[(start, end, line, body)] of the formulas; the delimiters that do not pair are told in `found`."""
    out, opened = [], None  # (position, token) of the formula open now
    for position, token in tokens(text):
        if opened is not None and opened[1] not in BLOCKS and "\n" in text[opened[0] : position]:
            found.append(f"Line {line_of(text, opened[0])}: {opened[1]} opens maths that does not close on its line.")
            opened = None  # (maths in a line closes on that line; $$ … $$ may take several)
        if opened is None:
            if token in OPENERS:
                opened = (position, token)
            else:
                found.append(f"Line {line_of(text, position)}: {token} closes maths that was never opened.")
        elif token == OPENERS[opened[1]]:
            start, opener = opened
            body = text[start + len(opener) : position]
            out.append((start, position + len(token), line_of(text, start), body))
            opened = None
    if opened is not None:
        found.append(f"Line {line_of(text, opened[0])}: {opened[1]} opens maths and nothing closes it.")
    return out


def check_formula(line, body, found):
    depth, i = 0, 0
    while i < len(body):
        if body[i] == "\\":
            i += 2  # \{ and \} are literal braces
            continue
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            if depth == 0:
                found.append(f"Line {line}: a }} closes a brace that was never opened.")
            depth = max(depth - 1, 0)
        i += 1
    if depth:
        found.append(f"Line {line}: {depth} {{ {'is' if depth == 1 else 'are'} never closed with }}.")
    stack = []
    for verb, name in ENVIRONMENT.findall(body):
        name = name.strip()
        if verb == "begin":
            stack.append(name)
        elif not stack:
            found.append(f"Line {line}: \\end{{{name}}} has no \\begin{{{name}}} before it.")
        else:
            if stack[-1] != name:
                found.append(f"Line {line}: \\end{{{name}}} closes \\begin{{{stack[-1]}}}.")
            stack.pop()
    found.extend(f"Line {line}: \\begin{{{name}}} has no \\end{{{name}}}." for name in stack)


def safe_source(src):
    """https://…, a path on the site (/…) or a relative one; never another scheme (javascript:, data:, http:)."""
    if src.lower().startswith("https://"):
        return True
    return bool(src) and not src.startswith("//") and not re.match(r"[a-z][a-z0-9+.-]*:", src, re.I)


def problems(text):
    """The problems of a Markdown text with LaTeX, as sentences; [] when it may be saved."""
    found = []
    text = blanked(CODE_SPAN, blanked(FENCED, blanked(COMMENT, text or "")))
    for match in FORBIDDEN.finditer(text):
        found.append(f"Line {line_of(text, match.start())}: \\{match.group(1)} is not allowed (links and pictures go "
                     "in the Markdown, not in the maths).")  # fmt: skip
    prose = text
    for start, end, line, body in formulas(text, found):
        check_formula(line, body, found)
        prose = blank(prose, start, end)  # what looks like HTML in maths is maths ($x<y$)
    for match in HTML_TAG.finditer(prose):
        found.append(f"Line {line_of(prose, match.start())}: raw HTML (<{match.group(1)}>) is not allowed: write "
                     "Markdown.")  # fmt: skip
    for match in IMAGE.finditer(prose):
        alt, src, title = match.group(1).strip(), match.group(2), (match.group(3) or "").strip().lower()
        line = line_of(prose, match.start())
        if not alt and title != "decorative":
            found.append(
                f'Line {line}: a picture needs its alt text (what it shows), or the title "decorative" when it '
                'only decorates: ![](picture.png "decorative").'
            )
        if not safe_source(src):
            found.append(f"Line {line}: a picture comes from an https:// address or the site itself.")
    return found


if __name__ == "__main__":  # python content/latex.py
    assert problems("| Step | Marks |\n|---|---|\n| $I = \\dfrac{\\varepsilon}{R+r}$ | 1 |") == []
    assert problems("$$\\begin{pmatrix}1\\\\2\\end{pmatrix}$$ and \\(x<y\\), `$5`, <!-- a note -->, a < b") == []
    assert problems("$-\\dfrac{1}{63}\\begin{pmatrix}(-8)(19)\\\\(-6)(19)\\end{pmatrix}$") == []
    for bad in ["$x", "$$x", "\\(x", "x\\]", "$\\frac{1}{2$", "$x}$", "$\\begin{matrix}1\\end{pmatrix}$"]:
        assert problems(bad), bad
    assert problems("$a\n$b$") and problems("$\\href{https://x}{y}$") and problems("\\url{x}")
    assert problems("<b>bold</b>") and problems("![](d.png)") and not problems('![](d.png "decorative")')
    assert problems("![x](javascript:alert(1))") and not problems("![A circuit](https://media.examleaf.in/c.png)")
    print("ok")
