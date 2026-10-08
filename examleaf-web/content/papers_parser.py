"""The Markdown parser of the books, vendored: parse_paper, parse_solutions and split_marks (and the subjects' codes and
the edition years) copied from production/build/book.py of the books repository LazyIndianBook/Class-12-Assam, commit
0e64cdf (8 October 2026). That file is the source of truth: when it changes how papers or solutions are written, copy
the functions again (only ruff's formatting differs) and run content/tests.py, whose papers are copies too.
"""
# ruff: noqa: E741  (book.py's names, kept so that the two can be compared)

import re

SUBJECTS = {
    "physics": dict(code="PHY", name="Physics"),
    "chemistry": dict(code="CHE", name="Chemistry"),
    "mathematics": dict(code="MAT", name="Mathematics"),
    "biology": dict(code="BIO", name="Biology"),
}
YEAR = "2026"
EXAM_YEAR = "2027"


def parse_paper(path):
    L = open(path).read().split("\n")
    P = dict(title=L[0][2:].strip(), header=[], allot=[], body=[])
    i = 1
    while i < len(L) and L[i].strip() != "---":  # header part
        l = L[i].rstrip()
        if l.startswith("|"):
            P["allot"].append(l)
        elif l.strip():
            P["header"].append(l)
        i += 1
    i += 1
    body = []  # list of dicts: kind, text, extras
    cur = None

    def flush():
        nonlocal cur
        if cur:
            body.append(cur)
            cur = None

    while i < len(L):
        l = L[i].rstrip()
        i += 1
        s = l.strip()
        if not s:
            continue
        if s.startswith("<!--"):
            continue
        if s.startswith("## "):
            flush()
            body.append(dict(kind="part", text=s[3:].strip()))
            continue
        if s == "**OR**":
            flush()
            body.append(dict(kind="or"))
            cur = None
            continue
        if s.startswith("|"):
            if cur is not None and cur["kind"] in ("q", "alt"):
                cur.setdefault("table", []).append(s)
                continue
        if s.startswith("**") and "`" in s and re.match(r"^\*\*\d+\.", s):  # group heading with marks code
            flush()
            m = re.match(r"^\*\*(.+?)\*\*\s*(?:&nbsp;)?\s*`([^`]+)`", s)
            body.append(dict(kind="group", text=m.group(1), marks=m.group(2)))
            continue
        if s.startswith("**") and s.endswith("**"):
            flush()
            body.append(dict(kind="instr", text=s[2:-2]))
            continue
        if s.startswith("> *Figure:*"):
            if cur:
                cur.setdefault("figure", []).append(s[len("> *Figure:*") :].strip())
                continue
        m = re.match(r"^(\d+)\.\s+(.*)$", s) or re.match(r"^(\([a-o]\))\s+(.*)$", s)
        if m and not (m.group(1) == "(i)" and "&nbsp;&nbsp; (ii)" in s):
            flush()
            cur = dict(kind="q", label=m.group(1) if m.group(1).startswith("(") else m.group(1) + ".", text=m.group(2))
            continue
        if "&nbsp;&nbsp; (ii)" in s and cur is not None:
            cur["options"] = [o.strip() for o in s.split("&nbsp;&nbsp;")]
            continue
        # text after an OR, or a continuation line (after an embedded table)
        prev = body[-1] if body and cur is None else None
        if cur is None and prev is not None and prev["kind"] == "or":
            cur = dict(kind="alt", text=s)
            continue
        if cur is not None:
            cur["text"] += "\n" + s
            continue
        body.append(dict(kind="instr", text=s))
    flush()
    P["body"] = body
    return P


def split_marks(text):
    """returns (question text, marks string) — the marks bracket **[…]** ends the question"""
    m = re.search(r"\s*\*\*\[([^\]]+)\]\*\*\s*$", text)
    return (text[: m.start()].rstrip(), m.group(1)) if m else (text, "")


def parse_solutions(path):
    L = open(path).read().split("\n")
    items = []
    cur = None
    for l in L[1:]:
        s = l.rstrip()
        if s.startswith("### "):
            if cur:
                items.append(cur)
            cur = dict(label=s[4:].strip(), lines=[])
            continue
        if cur is not None:
            cur["lines"].append(s)
    if cur:
        items.append(cur)
    return items
