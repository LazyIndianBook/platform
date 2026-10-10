"""Print a conflicted file's hunks: hunks.py [--edges N] [--width W] file..."""
import sys
args = sys.argv[1:]; edges = None; width = 160
while args and args[0].startswith("--"):
    flag = args.pop(0)
    if flag == "--edges": edges = int(args.pop(0))
    elif flag == "--width": width = int(args.pop(0))
for file in args:
    lines = open(file).read().split("\n")
    i = 0; n = 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<< "):
            n += 1; start = i
            mid = next(j for j in range(i, len(lines)) if lines[j] == "=======")
            end = next(j for j in range(mid, len(lines)) if lines[j].startswith(">>>>>>> "))
            ours, theirs = lines[start + 1:mid], lines[mid + 1:end]
            print(f"=== {file} hunk {n} at {start + 1}-{end + 1}: ours {len(ours)} lines, theirs {len(theirs)} lines ===")
            def show(side, rows, offset):
                if edges and len(rows) > 2 * edges:
                    picked = [(offset + k, rows[k]) for k in range(edges)] + [(None, f"... {len(rows) - 2 * edges} more ...")] + [(offset + k, rows[k]) for k in range(len(rows) - edges, len(rows))]
                else:
                    picked = [(offset + k, rows[k]) for k in range(len(rows))]
                for no, row in picked:
                    print(f"{side}{'' if no is None else no + 1:>6} {row[:width]}")
            show("<", ours, start + 1); print("-------"); show(">", theirs, mid + 1)
            i = end + 1
        else:
            i += 1
    if n == 0: print(f"=== {file}: no conflict markers ===")
