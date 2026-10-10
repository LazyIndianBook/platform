"""Resolve git conflict hunks by keeping both sides: ours first, then theirs (for files where both sides only added).
Usage: union.py [--theirs-first] file..."""

import re
import sys

args = sys.argv[1:]
theirs_first = "--theirs-first" in args
files = [a for a in args if not a.startswith("--")]
pattern = re.compile(r"^<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n", re.S | re.M)
for path in files:
    text = open(path, encoding="utf-8").read()
    count = 0

    def repl(match):
        global count
        count += 1
        ours, theirs = match.group(1), match.group(2)
        return theirs + ours if theirs_first else ours + theirs

    text = pattern.sub(repl, text)
    assert "<<<<<<<" not in text and ">>>>>>>" not in text, path
    open(path, "w", encoding="utf-8").write(text)
    print(f"{path}: {count} hunks united")
