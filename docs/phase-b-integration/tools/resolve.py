"""resolve_hunk(file, n, text): replace the n-th conflict hunk (1-based, markers included) with text; a callable gets
(ours, theirs), each side's text with its trailing newline."""
from pathlib import Path
def hunks(text):
    out, i = [], 0
    while True:
        a = text.find("<<<<<<< ", i)
        if a < 0: return out
        b = text.index("\n=======\n", a); c = text.index("\n>>>>>>> ", b); d = text.index("\n", c + 1) + 1
        out.append((a, d, text[a + text[a:].index("\n") + 1:b + 1], text[b + 9:c + 1]))
        i = d
def resolve_hunk(file, n, text):
    p = Path(file); src = p.read_text(); a, d, ours, theirs = hunks(src)[n - 1]
    if callable(text): text = text(ours, theirs)
    assert text.endswith("\n")
    p.write_text(src[:a] + text + src[d:]); print(f"{file}: hunk {n} resolved by hand")
