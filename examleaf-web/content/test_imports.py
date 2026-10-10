"""The import from the books repository as a staff job (plan 5.10): a dry run answers created, updated, unchanged,
unmatched and removed with the labels and writes nothing; its apply (which names it) writes only what changed, so the
history stays readable; a question no longer in the repository is unpublished and kept, never deleted; a commit is
read with git; the command does the same from the shell."""

import shutil
import subprocess
from io import StringIO

import pytest
from django.core.management import call_command

from accounts import roles
from staff.models import Job

from . import imports
from .conftest import STAFF, events, make_staff, signed_in
from .imports import FIXTURES
from .models import Paper, Question, Solution

pytestmark = pytest.mark.django_db
PHYSICS = {"papers": 4, "questions": 220}  # the test copies: PHY-E01, E02, M01, H01


@pytest.fixture
def importer(settings):
    settings.STAFF_TEST_MODE = True  # the test copies are for a test site
    return make_staff(roles.REVIEWER)


def start(client, params, dry_run, capture):
    with capture(execute=True):  # the job runs as its task would (eager Celery once committed)
        answer = client.post(STAFF + "jobs/", {"kind": "content_import", "params": params, "dry_run": dry_run},
                             format="json")  # fmt: skip
    assert answer.status_code == 202, answer.content
    return Job.objects.get(pk=answer.json()["id"])


def test_a_dry_run_counts_and_writes_nothing_then_its_apply_writes_what_changed(
    importer, django_capture_on_commit_callbacks
):
    client = signed_in(importer)
    params = {"subject": "physics", "commit": "", "fixtures": True}
    dry = start(client, params, True, django_capture_on_commit_callbacks)
    assert dry.state == "done", dry.errors
    counts = dry.result["counts"]
    assert counts == {"created": 1 + 4 + 2 * 220, "updated": 0, "unchanged": 0, "unmatched": 0, "removed": 0}
    assert dry.result["rows"]["created"][:2] == ["physics-2027: book", "PHY-E01: paper"]
    assert (dry.result["papers"], dry.result["questions"]) == (PHYSICS["papers"], PHYSICS["questions"])
    assert (dry.done, dry.total) == (4, 4) and not Paper.objects.exists()  # nothing written

    refused = client.post(STAFF + "jobs/", {"kind": "content_import", "params": params}, format="json")
    assert refused.status_code == 400 and "dry_run_job" in refused.json()["params"]  # an apply follows a dry run
    applied = start(client, {**params, "dry_run_job": dry.pk}, False, django_capture_on_commit_callbacks)
    assert applied.state == "done" and applied.result["counts"] == counts
    assert Question.objects.filter(paper__book__subject__code="PHY").count() == PHYSICS["questions"]
    assert events("content.imported").get().details["counts"]["created"] == counts["created"]

    again = start(client, params, True, django_capture_on_commit_callbacks)
    assert again.result["counts"]["unchanged"] == counts["created"] and again.result["counts"]["created"] == 0
    listed = client.get(STAFF + "content/imports/").json()["results"]
    assert [row["id"] for row in listed] == [again.pk, applied.pk, dry.pk]


def test_only_what_changed_is_written_and_a_removed_question_is_unpublished_not_deleted(
    importer, settings, tmp_path, django_capture_on_commit_callbacks
):
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    settings.PAPERS_ROOT = str(tmp_path)
    call_command("import_papers", "--subject", "physics", stdout=StringIO())
    gone = Question.objects.create(paper=Paper.objects.get(code="PHY-E01"), order=99, label="99", text_md="Old.")
    solutions = tmp_path / "production/physics/papers_md/PHY-E01-solutions.md"
    text = solutions.read_text()
    solutions.write_text(text.replace("**Ans.** square *(1)*", "**Ans.** a square *(1)*", 1))
    history = {model: model.history.count() for model in (Question, Solution, Paper)}

    client = signed_in(importer)
    params = {"subject": "physics", "commit": ""}
    dry = start(client, params, True, django_capture_on_commit_callbacks)
    assert dry.result["counts"]["updated"] == 1 and dry.result["counts"]["removed"] == 1
    assert dry.result["rows"]["updated"] == ["PHY-E01 1(a): solution"]
    assert dry.result["rows"]["removed"] == ["PHY-E01 99: question no longer in the repository"]
    applied = start(client, {**params, "dry_run_job": dry.pk}, False, django_capture_on_commit_callbacks)
    assert applied.state == "done", applied.errors
    gone.refresh_from_db()  # unpublished and kept, with its history
    assert gone.is_published is False and gone.history.first().history_change_reason.endswith("books repository")
    assert Solution.objects.get(question__paper__code="PHY-E01", question__label="1(a)").body_md.startswith(
        "**Ans.** a square"
    )
    # one new version for the solution that changed, one for the question unpublished, none for the rest
    assert Solution.history.count() == history[Solution] + 1 and Question.history.count() == history[Question] + 1
    assert Paper.history.count() == history[Paper]
    # back in the repository: shown again
    assert "99" not in [q.label for q in Question.objects.filter(paper__code="PHY-E01", is_published=True)]


def test_without_git_an_apply_still_refuses_a_folder_that_changed_since_its_dry_run(
    importer, settings, tmp_path, monkeypatch, django_capture_on_commit_callbacks
):
    """A deployed image mounts the books' folder alone (no git, no .git): the folder's fingerprint stands for the
    commit, so an apply still notices the folder moved."""
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    settings.PAPERS_ROOT = str(tmp_path)
    monkeypatch.setattr(imports, "head_commit", lambda root: None)
    client = signed_in(importer)
    dry = start(client, {"subject": "physics", "commit": ""}, True, django_capture_on_commit_callbacks)
    assert dry.state == "done" and dry.result["commit"].startswith("folder:"), dry.errors
    same = start(client, {"subject": "physics", "commit": ""}, True, django_capture_on_commit_callbacks)
    assert same.result["commit"] == dry.result["commit"]  # nothing moved: the same fingerprint
    solutions = tmp_path / "production/physics/papers_md/PHY-E01-solutions.md"
    solutions.write_text(solutions.read_text().replace("**Ans.** square *(1)*", "**Ans.** a square *(1)*", 1))
    moved = start(client, {"subject": "physics", "commit": "", "dry_run_job": dry.pk}, False,
                  django_capture_on_commit_callbacks)  # fmt: skip
    assert moved.state == "failed" and "moved since the dry run" in moved.errors[0]["message"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_a_commit_of_the_books_repository_is_read_and_an_apply_refuses_a_moved_repository(
    importer, settings, tmp_path, django_capture_on_commit_callbacks
):
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    settings.PAPERS_ROOT = str(tmp_path)

    def git(*args):
        command = ["git", "-C", str(tmp_path), "-c", "user.email=e2e@example.com", "-c", "user.name=E2E", *args]
        return subprocess.run(command, check=True, capture_output=True).stdout.decode().strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "the test papers")
    first = git("rev-parse", "HEAD")
    call_command("import_papers", "--subject", "physics", stdout=StringIO())
    solutions = tmp_path / "production/physics/papers_md/PHY-E01-solutions.md"
    solutions.write_text(solutions.read_text().replace("**Ans.** square *(1)*", "**Ans.** a square *(1)*", 1))
    git("commit", "-q", "-am", "a fix")

    client = signed_in(importer)
    at_first = start(client, {"subject": "physics", "commit": first[:10]}, True, django_capture_on_commit_callbacks)
    assert at_first.result["commit"] == first and at_first.result["counts"]["updated"] == 0  # the old text: as in
    now = start(client, {"subject": "physics", "commit": ""}, True, django_capture_on_commit_callbacks)
    assert now.result["counts"]["updated"] == 1 and now.result["commit"] == git("rev-parse", "HEAD")
    git("commit", "-q", "--allow-empty", "-m", "moved on")
    moved = start(client, {"subject": "physics", "commit": "", "dry_run_job": now.pk}, False,
                  django_capture_on_commit_callbacks)  # fmt: skip
    assert moved.state == "failed" and "moved since the dry run" in moved.errors[0]["message"]
    bad = client.post(STAFF + "jobs/", {"kind": "content_import", "params": {"subject": "physics", "commit": "main"},
                                        "dry_run": True}, format="json")  # fmt: skip
    assert bad.status_code == 400 and "commit" in bad.json()["params"]


def test_the_test_copies_are_for_a_test_site_and_the_import_is_the_reviewers(settings):
    settings.STAFF_TEST_MODE = False
    owner = signed_in(make_staff(roles.OWNER))
    params = {"kind": "content_import", "params": {"subject": "physics", "fixtures": True}, "dry_run": True}
    answer = owner.post(STAFF + "jobs/", params, format="json")
    assert answer.status_code == 400 and "fixtures" in answer.json()["params"]
    editor = signed_in(make_staff(roles.CONTENT_EDITOR))
    assert editor.post(STAFF + "jobs/", params, format="json").status_code == 403  # staff.import_content
    # high: a reviewer whose authentication is an hour old confirms it first
    stale = signed_in(make_staff(roles.REVIEWER), reauth=False).post(STAFF + "jobs/", params, format="json")
    assert stale.status_code == 403 and stale.json()["code"] == "reauthentication_required"


def test_the_command_still_imports_and_says_what_a_dry_run_would_do():
    out = StringIO()
    call_command("import_papers", "--subject", "physics", "--fixtures", "--dry-run", stdout=out)
    assert "a dry run: nothing written" in out.getvalue() and not Paper.objects.exists()
    call_command("import_papers", "--subject", "physics", "--fixtures", stdout=out)
    assert Paper.objects.count() == PHYSICS["papers"]
