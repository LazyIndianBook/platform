"""Import the Markdown sample papers and solutions of the books repository LazyIndianBook/Class-12-Assam: the service
`manage.py import_papers` and the panel's job (Job.Kind.CONTENT_IMPORT, staff.import_content) both call.

Parsing is content/papers_parser.py's (parse_paper, parse_solutions, split_marks), vendored from the books
repository's production/build/book.py. Only what changed is written, each field that changed (simple-history keeps
real edits, not import noise; a draft saved meanwhile is left alone); a question no longer in the repository is
unpublished and kept with its history, never deleted. A dry run reads and compares and writes nothing, so it answers
exactly what its apply would do: created, updated, unchanged, unmatched and removed, with the labels. The panel reads
the folder PAPERS_ROOT as it is, or production/<subject>/ of a commit of it (git archive), or the test copies of
content/fixtures/papers/ on a test site; its apply names the dry run it follows, which read the same commit."""

import hashlib
import io
import json
import re
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from staff import audit
from staff.models import Job

from . import papers_parser
from .models import Board, Book, ClassLevel, Paper, Question, Solution, Subject

SUBJECTS = ("physics", "chemistry", "mathematics", "biology")
EDITORIAL_NOTE = re.compile(r"\s*\((?:syllabus-only|Hard tier only|latter part)[^)]*\)")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "papers"
COMMIT = re.compile(r"[0-9a-f]{7,40}")
OUTCOMES = ("created", "updated", "unchanged", "unmatched", "removed")
ROWS_KEPT = 2000  # the labels a result keeps per outcome (the counts are whole)
DRY_RUN_HOURS = 24  # an apply follows a dry run this recent
REASON = "import_papers"  # each version's change reason in the history


def papers_root(root=None, fixtures=False):
    """The books checkout to read: the test copies with --fixtures, else --root, else the PAPERS_ROOT setting."""
    root = FIXTURES if fixtures else root or settings.PAPERS_ROOT
    if not root or not (Path(root) / "production").is_dir():
        raise CommandError(
            f"No production/ folder in {root or 'PAPERS_ROOT (not set)'}: give --root a checkout of the books "
            "repository LazyIndianBook/Class-12-Assam, set PAPERS_ROOT, or use --fixtures (the test copies)."
        )
    return Path(root)


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


class Report:
    """The counts of an import and the labels behind them (ROWS_KEPT a kind)."""

    def __init__(self):
        self.counts = dict.fromkeys(OUTCOMES, 0)
        self.rows = {outcome: [] for outcome in OUTCOMES if outcome != "unchanged"}

    def add(self, outcome, label):
        self.counts[outcome] += 1
        if outcome in self.rows and len(self.rows[outcome]) < ROWS_KEPT:
            self.rows[outcome].append(label)


def saved(obj):
    return obj is not None and obj.pk is not None


def upsert(model, lookup, values, report, label, write):
    """The record of `lookup` made, or updated in the fields that changed only (simple-history then keeps real edits,
    and a draft saved meanwhile stays), or left alone. Without `write` (a dry run) nothing is saved: a new record is
    answered unsaved."""
    if all(not hasattr(value, "_meta") or saved(value) for value in lookup.values()):
        rows = model.objects.filter(**lookup)
        obj = (rows.select_for_update() if write else rows).first()
    else:
        obj = None  # its parent is new in a dry run
    if obj is None:
        obj, changed = model(**lookup, **values), None
        report.add("created", label)
    else:
        changed = [name for name, value in values.items() if getattr(obj, name) != value]
        if not changed:
            report.add("unchanged", label)
            return obj
        for name in changed:
            setattr(obj, name, values[name])
        report.add("updated", label)
    if write:
        obj._change_reason = REASON
        obj.save(update_fields=changed)  # None: every field of a new one
    return obj


def import_subject(root, subject, *, dry_run=False, progress=None):
    """One subject of `root` (a folder holding production/): compared, and written unless `dry_run`; each paper in a
    transaction of its own (a second import of the subject waits for it), counted on `progress` (a job's)."""
    write = not dry_run
    meta = papers_parser.SUBJECTS[subject]
    subject_dir = Path(root) / "production" / subject
    fmt = json.loads((subject_dir / "format.json").read_text())
    prefixes = {p["name"].upper(): p["prefix"] for p in fmt.get("parts", []) if p.get("name")}
    tags = load_tags(subject_dir)
    paths = sorted((subject_dir / "papers_md").glob(f"{meta['code']}-[EMH][0-9][0-9].md"))
    report = Report()
    stats = dict(subject=subject, papers=0, questions=0, solutions=0, tagged=0, unmatched=[], missing=[], report=report)
    if progress is not None:
        progress.job.total = len(paths)
        progress.save()

    with transaction.atomic():
        board = Board.objects.filter(short_name="ASSEB").first()
        level = ClassLevel.objects.filter(number=12).first()
        subj = Subject.objects.filter(board=board, class_level=level, code=meta["code"]).first() if board else None
        if write:
            board = board or Board.objects.create(
                short_name="ASSEB", name="Assam State School Education Board", state="Assam"
            )
            level = level or ClassLevel.objects.create(number=12)
            subj, _ = Subject.objects.update_or_create(
                board=board, class_level=level, code=meta["code"], defaults=dict(name=meta["name"])
            )
        book = upsert(
            Book,
            dict(slug=f"{subject}-{papers_parser.EXAM_YEAR}"),
            dict(
                title=f"ExamLeaf {meta['name']} Sample Papers {papers_parser.EXAM_YEAR}",
                subject=subj or Subject(code=meta["code"], name=meta["name"]),
                edition=f"First edition, {papers_parser.YEAR}",
                cover=f"img/{subject}.png",
            ),
            report,
            f"{subject}-{papers_parser.EXAM_YEAR}: book",
            write,
        )

    for path in paths:
        with transaction.atomic():
            if write:  # one import of a subject at a time: a second one waits here, then finds it unchanged
                Subject.objects.select_for_update().filter(pk=subj.pk).first()
            import_paper(path, book, meta, fmt, prefixes, tags, stats, write)
        stats["papers"] += 1
        if progress is not None:
            progress.row()
    return stats


def import_paper(path, book, meta, fmt, prefixes, tags, stats, write):
    report = stats["report"]
    code = path.stem
    tier, number = code[-3], int(code[-2:])
    P = papers_parser.parse_paper(str(path))
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
        report,
        f"{code}: paper",
        write,
    )
    parsed = derive_questions(P, prefixes, papers_parser.split_marks)
    labels = [q.pop("label") for q in parsed]
    existing = {q.label: q for q in paper.questions.prefetch_related("tags")} if saved(paper) else {}
    solutions = {
        s["label"]: "\n".join(s["lines"]).strip()
        for s in papers_parser.parse_solutions(str(path.with_name(code + "-solutions.md")))
    }
    for label in solutions:
        if label not in labels:
            stats["unmatched"].append(f"{code} {label}")
            report.add("unmatched", f"{code} {label}: a solution with no question")
    for order, (label, values) in enumerate(zip(labels, parsed, strict=True), 1):
        values = dict(values, order=order, is_published=True)  # back in the repository: shown again
        q = upsert(Question, dict(paper=paper, label=label), values, report, f"{code} {label}: question", write)
        stats["questions"] += 1
        if label in solutions:
            upsert(
                Solution, dict(question=q), dict(body_md=solutions[label]), report, f"{code} {label}: solution", write
            )
            stats["solutions"] += 1
        else:
            stats["missing"].append(f"{code} {label}")
            report.add("unmatched", f"{code} {label}: a question with no solution")
        names = tags.get(f"{code}:{label}", [])
        if names:
            stats["tagged"] += 1
            old = existing.get(label)
            if write and (old is None or {t.name for t in old.tags.all()} != set(names)):
                q.tags.set(names)
    if not saved(paper):
        return
    for gone in paper.questions.exclude(label__in=labels).filter(is_published=True).order_by("order"):
        report.add("removed", f"{code} {gone.label}: question no longer in the repository")
        if write:  # unpublished and kept with its history, never deleted (its quiz items and clips keep their link)
            gone.is_published = False
            gone._change_reason = f"{REASON}: no longer in the books repository"
            gone.save(update_fields=["is_published"])


# ---- The panel's job (staff.jobs: Job.Kind.CONTENT_IMPORT) ----


def git(root, *args):
    """git's answer (bytes) in the books checkout; CommandError in words when it cannot give one."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=120, check=False)
    except FileNotFoundError as error:
        raise CommandError("git is not installed here: leave the commit empty to import the folder.") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError("git did not answer within 2 minutes.") from error
    if done.returncode:
        problem = done.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["no answer"]
        raise CommandError(f"git could not read the books repository at that commit: {problem[0][:200]}")
    return done.stdout


def folder_fingerprint(root, subject):
    """What production/<subject>/ holds, hashed from each file's path, size and time (no file is read), for the
    apply's check against its dry run where no git answers (a deployed image mounts the folder alone). Marked
    "folder:" so it is never mistaken for a commit."""
    digest = hashlib.sha256()
    folder = Path(root) / "production" / subject
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        stat = path.stat()
        digest.update(f"{path.relative_to(folder)}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return "folder:" + digest.hexdigest()[:40]


def head_commit(root):
    """The commit the folder is at, or None (not a git checkout, or no git here)."""
    try:
        return git(root, "rev-parse", "--verify", "HEAD").decode().strip() or None
    except CommandError:
        return None


@contextmanager
def source(root, subject, commit):
    """The folder to read: the checkout as it is, or production/<subject>/ of `commit` unpacked apart."""
    if not commit:
        yield root
        return
    with tempfile.TemporaryDirectory(prefix="examleaf-import-") as folder:
        archive = git(root, "archive", "--format=tar", commit, "--", f"production/{subject}")
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(folder, filter="data")
        yield Path(folder)


def recent_dry_run(pk):
    if not str(pk or "").isdigit():
        return None
    since = timezone.now() - timedelta(hours=DRY_RUN_HOURS)
    return Job.objects.filter(
        pk=int(pk), kind=Job.Kind.CONTENT_IMPORT, dry_run=True, state=Job.State.DONE, finished_at__gte=since
    ).first()


def clean_params(params, *, dry_run):
    """A job's parameters checked (staff.serializers.JobStartSerializer): the subject, the commit (empty: the folder
    as it is), the test copies (a test site only); an apply names a dry run of the same, done in the last 24 hours."""
    problems = {}
    subject = params.get("subject")
    if subject not in SUBJECTS:
        problems["subject"] = [f"One of {', '.join(SUBJECTS)}."]
    commit = str(params.get("commit") or "").strip().lower()
    if commit and not COMMIT.fullmatch(commit):
        problems["commit"] = ["A commit's hash: 7 to 40 of 0-9 and a-f; empty for the folder as it is."]
    fixtures = params.get("fixtures") is True
    if fixtures and not settings.STAFF_TEST_MODE:
        problems["fixtures"] = ["The test papers are for a test site only."]
    elif fixtures and commit:
        problems["commit"] = ["The test papers have no commits: leave it empty."]
    cleaned = {"subject": subject, "commit": commit, "fixtures": fixtures}
    if not dry_run and not problems:
        dry = recent_dry_run(params.get("dry_run_job"))
        if dry is None or {name: dry.params.get(name) for name in cleaned} != cleaned:
            problems["dry_run_job"] = [
                f"Run a dry run of this subject and commit first; its apply follows within {DRY_RUN_HOURS} hours."
            ]
        else:
            cleaned["dry_run_job"] = dry.pk
    if problems:
        raise serializers.ValidationError({"params": problems})
    return cleaned


def run_job(job, progress):
    """A dry run, or the apply of one: the subject read, compared and (applied) written; the counts and the labels
    as the job's result. An apply refuses to run when the repository moved since its dry run."""
    params = job.params
    root = papers_root(fixtures=params["fixtures"])
    if params["commit"]:
        commit = git(root, "rev-parse", "--verify", f"{params['commit']}^{{commit}}").decode().strip()
    elif params["fixtures"]:
        commit = None
    else:  # the checkout as it is: its commit, or, where no git answers, the folder's fingerprint
        commit = head_commit(root) or folder_fingerprint(root, params["subject"])
    if not job.dry_run:
        dry = recent_dry_run(params.get("dry_run_job"))
        if dry is None:
            raise CommandError(f"Its dry run is gone or older than {DRY_RUN_HOURS} hours: run a dry run again.")
        if dry.result.get("commit") != commit:
            raise CommandError("The books repository moved since the dry run: run a dry run again.")
    with source(root, params["subject"], params["commit"]) as folder:
        stats = import_subject(folder, params["subject"], dry_run=job.dry_run, progress=progress)
    report = stats["report"]
    result = {
        "subject": params["subject"],
        "commit": commit,
        "source": "fixtures" if params["fixtures"] else "repository",
        "papers": stats["papers"],
        "questions": stats["questions"],
        "counts": report.counts,
        "rows": report.rows,
    }
    if not job.dry_run:
        audit.record(
            "content.imported",
            actor=job.started_by,
            details={"job": job.pk, "subject": params["subject"], "commit": commit, "counts": report.counts},
        )
    return result
