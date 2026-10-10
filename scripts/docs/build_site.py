#!/usr/bin/env python3
"""The documentation portal's sources: every document of the repository copied into .docs-build/ at its own path (so
the links between documents keep working unchanged), GitHub's alerts turned into the portal's admonitions, links to
code files turned into links to the repository on GitHub, and the navigation of mkdocs.yml checked against what was
copied. Then `mkdocs build` (or `mkdocs serve`) reads .docs-build/. Usage: python scripts/docs/build_site.py"""
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".docs-build"
REPO = "https://github.com/LazyIndianBook/platform/blob/main/"
SKIP_DIRS = {"node_modules", ".venv", ".next", "site", ".docs-build", "fixtures", ".git", ".claude", "dist", "test-results", ".e2e"}
ALERT = re.compile(r"^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\n((?:> ?.*\n?)*)", re.M)
ADMONITION = {"NOTE": "note", "TIP": "tip", "IMPORTANT": "important", "WARNING": "warning", "CAUTION": "danger"}
LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")


def documents():
    for path in sorted(ROOT.rglob("*.md")):
        parts = set(path.relative_to(ROOT).parts)
        if not parts & SKIP_DIRS:
            yield path


def admonitions(text):
    """`> [!NOTE]` blocks become `!!! note` blocks (GitHub draws the first, the portal the second)."""
    def replace(match):
        lines = [line[2:] if line.startswith("> ") else line[1:] for line in match.group(2).rstrip("\n").split("\n")]
        spaced = []  # Python-Markdown needs a blank line before a list that follows a paragraph (GitHub does not)
        for line in lines:
            if re.match(r"\s*[-*] ", line) and spaced and spaced[-1].strip() and not re.match(r"\s*[-*] ", spaced[-1]):
                spaced.append("")
            spaced.append(line)
        indented = "\n".join("    " + line if line else "" for line in spaced)
        return f"!!! {ADMONITION[match.group(1)]}\n{indented}\n"
    return ALERT.sub(replace, text)


def code_links(text, path):
    """A link to a file that is not a document (a module, a setting file) points at the repository on GitHub."""
    def replace(match):
        label, target = match.groups()
        if "://" in target or target.startswith("#") or target.startswith("mailto:"):
            return match.group(0)
        file = target.split("#")[0]
        if not file:
            return match.group(0)
        resolved = (path.parent / file).resolve()
        if resolved == ROOT / "README.md":  # the repository's README is repository.md in the portal
            depth = len(path.relative_to(ROOT).parts) - 1
            return f"[{label}]({'../' * depth}repository.md{target[len(file):]})"
        if file.endswith(".md"):
            return match.group(0)
        resolved = (path.parent / file).resolve()
        try:
            relative = resolved.relative_to(ROOT)
        except ValueError:
            return match.group(0)
        if not resolved.exists():
            return match.group(0)
        return f"[{label}]({REPO}{relative.as_posix()})"
    return LINK.sub(replace, text)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    copied = []
    for path in documents():
        target = OUT / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code_links(admonitions(path.read_text()), path))
        copied.append(path.relative_to(ROOT).as_posix())
    # the assets (badges, the stylesheet, the hero), the design records' reports and screenshots, and the hub as the
    # home page
    shutil.copytree(ROOT / "docs" / "assets", OUT / "docs" / "assets", dirs_exist_ok=True)
    for path in (ROOT / "docs").rglob("*"):
        if path.suffix.lower() in {".html", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"} and "assets" not in path.parts:
            target = OUT / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    # the hub (docs/README.md) is the home page at the root: its links one level up lose their "../", the rest gain
    # "docs/"; the repository's README takes the name repository.md (README.md at the root would be the index)
    def home_links(match):
        label, target = match.groups()
        if "://" in target or target.startswith(("#", "mailto:")):
            return match.group(0)
        return f"[{label}]({target[3:] if target.startswith('../') else 'docs/' + target})"
    hub = (OUT / "docs" / "README.md").read_text()
    hub = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", home_links, hub).replace("](assets/", "](docs/assets/")
    (OUT / "index.md").write_text(hub.replace("](README.md)", "](repository.md)"))
    (OUT / "README.md").rename(OUT / "repository.md")
    copied[copied.index("README.md")] = "repository.md"
    class Loader(yaml.SafeLoader):  # mkdocs.yml names a Python object for the Mermaid fence; the nav is all we read
        pass

    Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)
    config = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=Loader)
    missing = []

    def walk(items):
        for item in items:
            for title, value in (item.items() if isinstance(item, dict) else [(None, item)]):
                if isinstance(value, list):
                    walk(value)
                elif isinstance(value, str) and value != "index.md" and value not in copied:
                    missing.append(value)
    walk(config.get("nav", []))
    print(f"{len(copied)} documents copied to {OUT.name}/")
    if missing:
        print("nav entries with no document:", *missing, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
