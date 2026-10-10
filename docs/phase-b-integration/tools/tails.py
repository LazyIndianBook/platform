"""Resolve an append-only file whose conflict split its tail: the merged prefix (the working tree up to the first
conflict marker), then HEAD's tail, then the branch's own section from its marker.
Usage: tails.py <file> <branch> <theirs-marker> [<head-marker>]
Without a head marker HEAD must start with the merged prefix (the branch changed nothing before its section); with
one, HEAD's tail starts at that marker (column 0) and the prefix is the working tree's (both sides' earlier edits)."""
import re, subprocess, sys
from pathlib import Path

file, branch, theirs_marker = sys.argv[1:4]
head_marker = sys.argv[4] if len(sys.argv) > 4 else None
show = lambda ref: subprocess.check_output(["git", "show", f"{ref}:{file}"], text=True)
wt = Path(file).read_text()
assert "<<<<<<< " in wt, "no conflict in " + file
prefix = wt[: wt.index("<<<<<<< ")]
head, theirs = show("HEAD"), show(branch)
def tail(text, marker):
    hits = [m.start() for m in re.finditer("^" + re.escape(marker), text, re.M)]
    assert len(hits) == 1, f"{marker!r} found {len(hits)} times at column 0"
    return text[hits[0]:]
if head_marker:
    head_tail = tail(head, head_marker)
else:
    assert head.startswith(prefix), "the branch changed lines before its section: give HEAD's marker"
    head_tail = head[len(prefix):]
sep = "\n\n\n" if file.endswith(".py") else "\n"
Path(file).write_text(prefix + head_tail.rstrip("\n") + "\n" + sep.lstrip("\n") + tail(theirs, theirs_marker))
out = Path(file).read_text()
assert "<<<<<<<" not in out and ">>>>>>>" not in out and "=======\n" not in out.replace("=======\n", "", 0)
print(f"{file}: prefix {prefix.count(chr(10))} lines + HEAD's tail {head_tail.count(chr(10))} + {branch[:20]}'s {tail(theirs, theirs_marker).count(chr(10))}")
