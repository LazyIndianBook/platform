"""Drafts and their review (plan 5.10): an edit of a published solution waits apart from the live text, a second
person who did not edit it approves and publishes it, a publish applies the draft and a rollback restores the text
before it; an edit after a submission cancels the review; a version from the history comes back (a solution's into
its draft, a book's at once); every step is audited and the inbox follows."""

import pytest
from rest_framework.test import APIClient

from accounts import roles
from staff.models import InboxItem

from .conftest import CONTENT, SOLUTION, events, make_paper, make_staff, narrowed, signed_in
from .models import Book, Question, ReviewTask, Solution

pytestmark = pytest.mark.django_db
FIXED = SOLUTION.replace("$I = 0.5$ A", "$I = 0.50$ A")


def public_solution(paper):
    return APIClient().get(f"/api/v1/papers/{paper.code}/solutions/").json()[0]["solution"]["markdown"]


@pytest.fixture(autouse=True)
def open_solutions(settings):
    settings.SOLUTIONS_REQUIRE_LOGIN = False  # the public API reads the live text without an account


def test_an_edit_writes_the_draft_and_the_site_keeps_the_live_text(editor):
    paper = make_paper()
    solution = Solution.objects.get()
    answer = signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    assert answer.status_code == 200, answer.content
    body = answer.json()
    assert (body["state"], body["body_md"], body["draft"]) == ("draft", SOLUTION, {"body_md": FIXED})
    assert body["draft_by"] == editor.pk and public_solution(paper) == SOLUTION  # nothing went live
    assert events("content.draft_saved").get().details["fields"] == ["body_md"]
    # typed back to the live text: no draft any more, nothing changed since the publish
    back = signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": SOLUTION}, format="json").json()
    assert (back["state"], back["draft"]) == ("published", {})


def test_bad_latex_is_refused_on_save_with_its_line(editor):
    make_paper()
    solution = Solution.objects.get()
    answer = signed_in(editor).patch(
        f"{CONTENT}solutions/{solution.pk}/", {"body_md": "| Step | Marks |\n|---|---|\n| $\\frac{1}{2$ | 1 |"},
        format="json",
    )  # fmt: skip
    assert answer.status_code == 400
    assert answer.json()["body_md"] == ["Line 3: 1 { is never closed with }."]
    dangerous = signed_in(editor).patch(
        f"{CONTENT}solutions/{solution.pk}/", {"body_md": "$\\href{https://x.example}{click}$ <script>"}, format="json"
    )
    assert dangerous.status_code == 400 and len(dangerous.json()["body_md"]) == 2
    assert Solution.objects.get().draft == {}


def test_author_checker_publish_and_the_last_editor_never_publishes(editor, reviewer):
    paper = make_paper()
    solution = Solution.objects.get()
    signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    submitted = signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json")
    assert submitted.status_code == 201, submitted.content
    task = ReviewTask.objects.get(pk=submitted.json()["id"])
    assert (task.state, task.stage, task.submitted_by, task.edited_by) == ("in_progress", "check", editor, editor)
    assert Solution.objects.get().state == "in_review"
    item = InboxItem.objects.get(kind=InboxItem.Kind.REVIEW, done_at=None)
    assert (item.permission, item.data["subject"], item.title) == (
        "staff.publish_paper",
        "PHY",
        "Review: PHY-E01 2(c), solution",
    )
    # a reviewer who also edits it is its last editor: someone else decides
    both = narrowed(roles.REVIEWER, "PHY")
    both.groups.add(*editor.groups.all())
    both = type(both).objects.get(pk=both.pk)
    signed_in(both).post(f"{CONTENT}solutions/{solution.pk}/discard/", {}, format="json")
    signed_in(both).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    mine = signed_in(both).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json").json()
    for verb in ("approve", "publish"):
        refused = signed_in(both).post(f"{CONTENT}reviews/{mine['id']}/{verb}/", {}, format="json")
        assert refused.status_code == 403 and refused.json()["code"] == "own_edit"
    assert public_solution(paper) == SOLUTION
    # the queue: "waiting for me" leaves out one's own
    queue = signed_in(both).get(f"{CONTENT}reviews/?mine=1").json()["results"]
    assert queue == [] and signed_in(reviewer).get(f"{CONTENT}reviews/?mine=1").json()["results"][0]["id"] == mine["id"]
    detail = signed_in(reviewer).get(f"{CONTENT}reviews/{mine['id']}/").json()
    assert detail["yours"] is False and detail["changes"][0]["field"] == "body_md"
    assert {"op": "delete", "text": "| $I = 0.5$ A | 1 |"} in detail["changes"][0]["lines"]
    assert {"op": "insert", "text": "| $I = 0.50$ A | 1 |"} in detail["changes"][0]["lines"]
    published = signed_in(reviewer).post(f"{CONTENT}reviews/{mine['id']}/publish/", {}, format="json")
    assert published.status_code == 200, published.content
    assert published.json()["state"] == "approved" and published.json()["published_by"] == reviewer.pk
    # published, the review still shows what it changed: the text it replaced against the text it put live
    lines = published.json()["changes"][0]["lines"]
    assert {"op": "delete", "text": "| $I = 0.5$ A | 1 |"} in lines and {
        "op": "insert",
        "text": "| $I = 0.50$ A | 1 |",
    } in lines
    assert public_solution(paper) == FIXED
    live = Solution.objects.get()
    assert (live.state, live.draft, live.published_by) == ("published", {}, reviewer)
    assert not InboxItem.objects.filter(kind=InboxItem.Kind.REVIEW, done_at=None).exists()
    assert [event.actor_id for event in events("content.published")] == [reviewer.pk]
    assert events("content.submitted").filter(actor_id=both.pk).exists()


def test_a_rollback_restores_the_text_before_the_publish(editor, reviewer):
    paper = make_paper()
    solution = Solution.objects.get()
    signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    task = signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json").json()
    signed_in(reviewer).post(f"{CONTENT}reviews/{task['id']}/publish/", {}, format="json")
    assert public_solution(paper) == FIXED
    rolled = signed_in(reviewer).post(f"{CONTENT}solutions/{solution.pk}/rollback/", {}, format="json")
    assert rolled.status_code == 200, rolled.content
    assert public_solution(paper) == SOLUTION  # the text before the publish, live again
    body = rolled.json()
    assert (body["state"], body["draft"]) == ("draft", {"body_md": FIXED})  # the work kept, to be reviewed again
    assert ReviewTask.objects.get(pk=task["id"]).rolled_back_by == reviewer
    again = signed_in(reviewer).post(f"{CONTENT}solutions/{solution.pk}/rollback/", {}, format="json")
    assert again.status_code == 400  # nothing published from the panel is live
    assert signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/rollback/", {}, format="json").status_code == 403
    assert events("content.rolled_back").count() == 1


def test_an_edit_after_submitting_cancels_the_review_and_changes_asked_go_back_to_the_editor(editor, reviewer):
    make_paper()
    solution = Solution.objects.get()
    client = signed_in(editor)
    client.patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    first = client.post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json").json()
    client.patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED + "\n\nAlso 0.5 A."}, format="json")
    assert ReviewTask.objects.get(pk=first["id"]).state == "cancelled"  # what was approved is what goes live
    assert Solution.objects.get().state == "draft"
    second = client.post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json").json()
    asked = signed_in(reviewer).post(f"{CONTENT}reviews/{second['id']}/needs-changes/", {}, format="json")
    assert asked.status_code == 400 and "comment" in asked.json()
    asked = signed_in(reviewer).post(
        f"{CONTENT}reviews/{second['id']}/needs-changes/", {"comment": "Keep the units in the table."}, format="json"
    )
    assert asked.status_code == 200 and asked.json()["state"] == "needs_changes"
    assert asked.json()["comments"][-1]["text"] == "Keep the units in the table."
    assert Solution.objects.get().state == "draft"
    item = InboxItem.objects.get(kind=InboxItem.Kind.REVIEW, done_at=None)
    assert (item.assignee, item.title) == (editor, "Changes asked: PHY-E01 2(c), solution")
    published = signed_in(reviewer).post(f"{CONTENT}reviews/{second['id']}/publish/", {}, format="json")
    assert published.status_code == 400  # sent back: nothing to publish


def test_a_question_drafts_its_text_and_changes_its_order_at_once(editor):
    make_paper(labels=("2(c)", "2(d)"))
    question = Question.objects.get(label="2(d)")
    answer = signed_in(editor).patch(
        f"{CONTENT}questions/{question.pk}/",
        {"text_md": "A cell of emf $6$ V.", "marks_text": "3", "order": 5, "tags": ["Ch 3: Current Electricity"]},
        format="json",
    )
    assert answer.status_code == 200, answer.content
    question.refresh_from_db()
    assert question.draft == {"text_md": "A cell of emf $6$ V.", "marks_text": "3"} and question.marks_text == "2"
    assert question.order == 5 and set(question.tags.names()) == {"Ch 3: Current Electricity"}
    clash = signed_in(editor).patch(f"{CONTENT}questions/{question.pk}/", {"label": "2(c)"}, format="json")
    assert clash.status_code == 400 and "label" in clash.json()


def test_the_history_reads_as_a_diff_and_a_version_comes_back(editor, reviewer):
    make_paper()
    solution = Solution.objects.get()
    signed_in(editor).patch(f"{CONTENT}solutions/{solution.pk}/", {"body_md": FIXED}, format="json")
    task = signed_in(editor).post(f"{CONTENT}solutions/{solution.pk}/submit/", {}, format="json").json()
    signed_in(reviewer).post(f"{CONTENT}reviews/{task['id']}/publish/", {}, format="json")
    versions = signed_in(editor).get(f"{CONTENT}solutions/{solution.pk}/history/").json()["results"]
    assert versions[0]["reason"].startswith("published (review #")
    live = next(change for change in versions[0]["changes"] if change["field"] == "body_md")
    assert (live["before"], live["after"]) == (SOLUTION, FIXED)
    first = versions[-1]
    assert first["type"] == "+" and first["changes"] == []
    restored = signed_in(editor).post(
        f"{CONTENT}solutions/{solution.pk}/history/{first['id']}/restore/", {}, format="json"
    )
    assert restored.status_code == 200, restored.content
    assert restored.json()["draft"] == {"body_md": SOLUTION} and Solution.objects.get().body_md == FIXED
    assert events("content.version_restored").get().details["restored"] == first["id"]
    # a book's version comes back at once
    book = Book.objects.get()
    signed_in(editor).patch(f"{CONTENT}books/{book.pk}/", {"edition": "Second edition, 2027"}, format="json")
    old = signed_in(editor).get(f"{CONTENT}books/{book.pk}/history/").json()["results"][-1]
    back = signed_in(editor).post(f"{CONTENT}books/{book.pk}/history/{old['id']}/restore/", {}, format="json")
    assert back.status_code == 200 and Book.objects.get().edition == "First edition, 2026"
    assert signed_in(editor).post(f"{CONTENT}books/{book.pk}/history/999999/restore/", {}).status_code == 404


def test_publishing_a_paper_needs_its_own_permission(editor, reviewer):
    paper = make_paper()
    refused = signed_in(editor).patch(f"{CONTENT}papers/{paper.pk}/", {"is_published": False}, format="json")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    assert signed_in(editor).patch(f"{CONTENT}papers/{paper.pk}/", {"title": "E-01"}, format="json").status_code == 200
    admin = make_staff(roles.ADMIN)
    done = signed_in(admin).patch(f"{CONTENT}papers/{paper.pk}/", {"is_published": False}, format="json")
    assert done.status_code == 200 and events("content.paper_unpublished").exists()
    assert APIClient().get(f"/api/v1/papers/{paper.code}/").status_code == 404
