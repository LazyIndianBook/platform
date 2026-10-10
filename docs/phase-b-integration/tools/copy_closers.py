"""copy.ts after a union: every top-level module block must be closed with `  },` before the next `  name: {`."""
import re
from pathlib import Path
p = Path("examleaf-admin/src/lib/copy.ts"); lines = p.read_text().split("\n"); fixed = 0
i = 1
while i < len(lines):
    if re.match(r"^  [a-zA-Z]+: \{$", lines[i]):
        j = i - 1
        while j >= 0 and (lines[j].startswith("  //") or lines[j].strip() == ""):
            j -= 1
        indent = len(lines[j]) - len(lines[j].lstrip(" "))
        if lines[j] != "  }," and indent >= 4:  # still inside the block before: close every open level
            closers = ["  " * level + "}," for level in range(indent // 2 - 1, 0, -1)]
            lines[j + 1:j + 1] = closers; fixed += 1; i += len(closers)
            print("closed the block before", lines[i].strip(), "after", repr(lines[j].strip()[:50]))
    i += 1
p.write_text("\n".join(lines)); print("copy.ts closers inserted:", fixed)
