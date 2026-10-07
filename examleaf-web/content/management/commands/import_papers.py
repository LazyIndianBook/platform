"""Import the Markdown sample papers and solutions of the book repository.

    python manage.py import_papers --root "<book repo>" --subject physics
    python manage.py import_papers --all

Parsing is done by production/build/book.py (parse_paper, parse_solutions, split_marks), loaded by path.
Re-running updates changed records only, so simple-history keeps real edits, not import noise.
"""

import importlib.util
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from content.models import Board, Book, ClassLevel, Paper, Question, Solution, Subject

SUBJECTS = ("physics", "chemistry", "mathematics", "biology")
EDITORIAL_NOTE = re.compile(r"\s*\((?:syllabus-only|Hard tier only|latter part)[^)]*\)")


def load_book_py(root):
    spec = importlib.util.spec_from_file_location("examleaf_book", Path(root) / "production" / "build" / "book.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def split_tables(rows):
    """parse_paper keeps all allotment rows in one list; a new table starts at each row followed by |---|."""
    tables = []
    for i, row in enumerate(rows):
        if not tables or (i + 1 < len(rows) and re.match(r"^\|\s*-{3,}", rows[i + 1])):
            tables.append([])
        tables[-1].append(row)
    return ["\n".join(t) for t in tables]


def derive_questions(P, prefixes, split_marks):
    """Questions of a parsed paper, in order, labelled as the solutions file labels them:
    "9." -> 9, "(a)" under group question 1 -> 1(a), Botany/Zoology parts -> B/Z prefix, alternative -> "<label> OR".
    A lettered line with no group heading open is a sub-part of the question above it (printed after its table)."""
    part = group = prefix = number = main = ""
    in_group = False
    out = []
    for b in P["body"]:
        kind = b["kind"]
        if kind == "part":
            part, group, in_group = b["text"], "", False
            prefix = next((p for name, p in prefixes.items() if name in part.upper()), "")
        elif kind == "group":
            group = f"{b['text']} `{b['marks']}`"
            number = re.match(r"\d+", b["text"]).group()
            in_group = True
        elif kind == "instr":
            group = b["text"]
        elif kind == "q" and b["label"].startswith("(") and not in_group and out:
            prev = out[-1]
            text, marks = split_marks(f"{b['label']} {b['text']}")
            prev["text_md"] += "\n\n" + "\n\n".join(filter(None, [prev["table_md"], text]))
            prev["table_md"], prev["marks_text"] = "", marks or prev["marks_text"]
        elif kind in ("q", "alt"):
            if kind == "alt":
                label = main + " OR"
            elif b["label"].startswith("("):
                label = main = f"{prefix}{number}{b['label']}"
            else:
                number, in_group = b["label"].rstrip("."), False
                label = main = prefix + number
            text, marks = split_marks(b["text"])
            for fig in b.get("figure", []):
                text += f"\n\n*Figure:* {fig}"
            out.append(
                dict(
                    label=label,
                    part_label=part,
                    group_label=group,
                    text_md=text,
                    marks_text=marks,
                    options_json=b.get("options", []),
                    table_md="\n".join(b.get("table", [])),
                    is_alternative=kind == "alt",
                )
            )
    return out


def load_tags(subject_dir):
    """{"PHY-E01:1(a)": ["Ch 1: Electric Charges and Fields", "§1.5 Coulomb's Law"]} from the work orders."""
    tags = {}
    for path in sorted((subject_dir / "orders").glob("ch*.md")):
        lines = path.read_text().splitlines()
        m = re.search(r"Chapter (\d+) · (.+)$", lines[0])
        chapter = f"Ch {m.group(1)}: {m.group(2).strip()}"[:100] if m else None
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and re.match(r"^[A-Z]{3}-[EMH]\d\d:", cells[0]):
                section = EDITORIAL_NOTE.sub("", cells[3])[:100]
                tags[cells[0]] = [t for t in (chapter, section) if t]
    return tags


def upsert(model, lookup, values, counts):
    """Create or update only when something changed (keeps simple-history free of no-op versions)."""
    obj = model.objects.filter(**lookup).first()
    if obj is None:
        obj, state = model(**lookup, **values), "created"
    else:
        changed = {k: v for k, v in values.items() if getattr(obj, k) != v}
        if not changed:
            counts["unchanged"] += 1
            return obj
        for k, v in changed.items():
            setattr(obj, k, v)
        state = "updated"
    obj._change_reason = "import_papers"
    obj.save()
    counts[state] += 1
    return obj


def import_subject(root, subject):
    root = Path(root)
    book_py = load_book_py(root)
    meta = book_py.SUBJECTS[subject]
    subject_dir = root / "production" / subject
    fmt = json.loads((subject_dir / "format.json").read_text())
    prefixes = {p["name"].upper(): p["prefix"] for p in fmt.get("parts", []) if p.get("name")}
    tags = load_tags(subject_dir)
    counts = dict(created=0, updated=0, unchanged=0)
    stats = dict(subject=subject, papers=0, questions=0, solutions=0, tagged=0, unmatched=[], missing=[], counts=counts)

    with transaction.atomic():
        board, _ = Board.objects.get_or_create(
            short_name="ASSEB", defaults=dict(name="Assam State School Education Board", state="Assam")
        )
        level, _ = ClassLevel.objects.get_or_create(number=12)
        subj, _ = Subject.objects.update_or_create(
            board=board, class_level=level, code=meta["code"], defaults=dict(name=meta["name"])
        )
        book = upsert(
            Book,
            dict(slug=f"{subject}-{book_py.EXAM_YEAR}"),
            dict(
                title=f"ExamLeaf {meta['name']} Sample Papers {book_py.EXAM_YEAR}",
                subject=subj,
                edition=f"First edition, {book_py.YEAR}",
                cover=f"img/{subject}.png",
            ),
            counts,
        )

        for path in sorted((subject_dir / "papers_md").glob(f"{meta['code']}-[EMH][0-9][0-9].md")):
            code = path.stem
            tier, number = code[-3], int(code[-2:])
            P = book_py.parse_paper(str(path))
            header = [h for h in P["header"] if "Full Marks" not in h and "Assam HS Final" not in h]
            paper = upsert(
                Paper,
                dict(code=code),
                dict(
                    book=book,
                    tier=tier,
                    number=number,
                    title=f"{meta['name']} Sample Paper {tier}-{number:02d}",
                    full_marks=fmt["full_marks"],
                    pass_marks=fmt["pass_marks"],
                    time_text=fmt["time"],
                    header_json=dict(lines=header, allotment=split_tables(P["allot"])),
                ),
                counts,
            )
            stats["papers"] += 1

            parsed = derive_questions(P, prefixes, book_py.split_marks)
            labels = [q.pop("label") for q in parsed]
            existing = {q.label: q for q in paper.questions.prefetch_related("tags")}
            solutions = {
                s["label"]: "\n".join(s["lines"]).strip()
                for s in book_py.parse_solutions(str(path.with_name(code + "-solutions.md")))
            }
            stats["unmatched"] += [f"{code} {label}" for label in solutions if label not in labels]
            for order, (label, values) in enumerate(zip(labels, parsed, strict=True), 1):
                q = upsert(Question, dict(paper=paper, label=label), dict(values, order=order), counts)
                stats["questions"] += 1
                if label in solutions:
                    upsert(Solution, dict(question=q), dict(body_md=solutions[label]), counts)
                    stats["solutions"] += 1
                else:
                    stats["missing"].append(f"{code} {label}")
                names = tags.get(f"{code}:{label}", [])
                if names:
                    stats["tagged"] += 1
                    old = existing.get(label)
                    if old is None or {t.name for t in old.tags.all()} != set(names):
                        q.tags.set(names)
            paper.questions.exclude(label__in=labels).delete()
    return stats


class Command(BaseCommand):
    help = "Import the sample papers and solutions (Markdown) of one subject or all four."

    def add_arguments(self, parser):
        parser.add_argument("--root", default=str(settings.BOOK_ROOT), help="root of the book repository")
        parser.add_argument("--subject", choices=SUBJECTS)
        parser.add_argument("--all", action="store_true")

    def handle(self, root, subject, all, **options):
        if not (subject or all):
            raise CommandError("Give --subject <name> or --all.")
        problems = 0
        for name in SUBJECTS if all else [subject]:
            s = import_subject(root, name)
            c = s["counts"]
            self.stdout.write(
                f"{name}: {s['papers']} papers, {s['questions']} questions, {s['solutions']} solutions matched, "
                f"{s['tagged']} tagged; records created {c['created']}, updated {c['updated']}, "
                f"unchanged {c['unchanged']}; unmatched solution labels: {len(s['unmatched'])}; "
                f"questions without a solution: {len(s['missing'])}"
            )
            for item in s["unmatched"]:
                self.stdout.write(f"  unmatched solution: {item}")
            for item in s["missing"]:
                self.stdout.write(f"  question without solution: {item}")
            problems += len(s["unmatched"]) + len(s["missing"])
        if problems:
            raise CommandError(f"{problems} labels did not match.")
