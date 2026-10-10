#!/usr/bin/env python3
"""Every Mermaid fence in the documents rendered once with the Mermaid command line (npx @mermaid-js/mermaid-cli), so
a diagram that does not parse fails before it is committed. Usage: python scripts/docs/check_mermaid.py [paths...]
(default: every Markdown document outside node_modules, .venv, fixtures and the build folders). Exit 1 on any error."""
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"node_modules", ".venv", ".next", "site", ".docs-build", "fixtures", ".git", ".claude", "dist"}
FENCE = re.compile(r"^```mermaid[^\n]*\n(.*?)^```", re.S | re.M)


def documents(paths):
    if paths:
        for p in paths:
            p = Path(p)
            yield from (p.rglob("*.md") if p.is_dir() else [p])
        return
    for path in ROOT.rglob("*.md"):
        if not SKIP & set(path.relative_to(ROOT).parts):
            yield path


def render(job):
    path, number, source, folder = job
    src = folder / f"{path.stem}-{number}.mmd"
    src.write_text(source)
    out = src.with_suffix(".svg")
    done = subprocess.run(
        ["npx", "-y", "@mermaid-js/mermaid-cli", "-q", "-i", str(src), "-o", str(out)],
        capture_output=True, text=True, timeout=180,
    )
    if done.returncode or not out.exists():
        message = (done.stderr or done.stdout).strip().splitlines()
        return f"{path.relative_to(ROOT)} diagram {number}: {message[-1][:200] if message else 'no answer'}"
    return None


def main():
    jobs = []
    with tempfile.TemporaryDirectory() as folder:
        for path in documents(sys.argv[1:]):
            text = path.read_text()
            for number, match in enumerate(FENCE.finditer(text), 1):
                jobs.append((path, number, match.group(1), Path(folder)))
        if not jobs:
            print("no Mermaid diagrams found")
            return 0
        workers = min(8, os.cpu_count() or 4)
        with ThreadPoolExecutor(workers) as pool:
            problems = [p for p in pool.map(render, jobs) if p]
    print(f"{len(jobs)} diagrams checked, {len(problems)} failed")
    for problem in problems:
        print(" ", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
