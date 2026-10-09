"""The Course module's content side (learn/staff_api.py, learn.course): the person's subjects narrowing the outline and
every record (404 for another subject's), moving a row in each of the four ways with a dense order, a revision's
review by someone else and its publish now or by the task at its time (once), the bin's restore and its purge taking
a clip's files only after 30 days, the bin hidden from the app's and the website's API, a failed clip's reason in
words and its retry, the quiz bank's statistics (N/A under 30 learners) and filters, "needs checking" filed once into
the content triage, the bank's bulk metadata job with its dry run, and the lists read with a fixed number of
queries."""

from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from api.tests import sign_in, student
from content.conftest import make_paper
from content.models import ErrorReport
from insights.models import ItemStat
from staff.models import InboxItem, Job

from . import course, media
from .conftest import COURSE, STAFF, events, make_staff, signed_in
from .models import CardReview, Chapter, Clip, Entitlement, FlashCard, Progress, QuizAttempt, QuizItem, Revision
from .tests import make_course

pytestmark = [pytest.mark.django_db, pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")]


def titles(revision):
    return list(Clip.objects.filter(revision=revision).order_by("order").values_list("title", "order"))


def queries(client, path):
    client.get(path)  # (the site's switches, read once into the cache)
    with CaptureQueriesContext(connection) as captured:
        assert client.get(path).status_code == 200, path
    return len(captured)


def chemistry():
    return make_course(subject=make_paper("CHE").book.subject, chapters=1, clips=1)


def test_the_outline_and_every_record_stay_within_the_persons_subjects(editor, physics):
    other = chemistry()
    client = signed_in(editor)
    assert [row["code"] for row in client.get(f"{COURSE}subjects/").json()] == ["PHY"]
    outline = client.get(f"{COURSE}subjects/{physics.pk}/outline/").json()
    first = outline["chapters"][0]
    assert [chapter["number"] for chapter in outline["chapters"]] == [1, 2]
    assert first["revision"]["status"] == "published" and first["revision"]["minutes"] == 6
    assert [(clip["title"], clip["order"], clip["free"]) for clip in first["revision"]["clips"]] == [
        ("Clip 1.1", 1, True),
        ("Clip 1.2", 2, False),
        ("Clip 1.3", 3, False),
    ]
    assert first["cards"][0]["front"] == "Front 1" and first["items"][0]["text"] == "Statement 1"
    assert outline["completion_rule"].startswith("A clip counts as completed")
    assert client.get(f"{COURSE}subjects/{other.pk}/outline/").status_code == 404
    foreign = Clip.objects.get(revision__chapter__subject=other)
    assert client.get(f"{COURSE}clips/{foreign.pk}/").status_code == 404
    assert client.patch(f"{COURSE}clips/{foreign.pk}/", {"title": "x"}, format="json").status_code == 404
    assert client.get(f"{COURSE}items/?subject=CHE").json()["results"] == []
    owner = signed_in(make_staff(roles.OWNER))
    assert [row["code"] for row in owner.get(f"{COURSE}subjects/").json()] == ["CHE", "PHY"]
    assert owner.get(f"{COURSE}clips/{foreign.pk}/").status_code == 200


def test_a_row_moves_first_last_before_and_after_keeping_a_dense_order(editor, physics):
    revision = Revision.objects.get(chapter__number=1)
    one, two, three = Clip.objects.filter(revision=revision).order_by("order")
    client = signed_in(editor)

    def move(clip, to, target=None):
        body = {"to": to, **({"target": target.pk} if target else {})}
        return client.post(f"{COURSE}clips/{clip.pk}/move/", body, format="json")

    assert move(three, "first").status_code == 200
    assert titles(revision) == [("Clip 1.3", 1), ("Clip 1.1", 2), ("Clip 1.2", 3)]
    assert move(three, "last").status_code == 200
    assert titles(revision) == [("Clip 1.1", 1), ("Clip 1.2", 2), ("Clip 1.3", 3)]
    assert move(one, "after", two).status_code == 200
    assert titles(revision) == [("Clip 1.2", 1), ("Clip 1.1", 2), ("Clip 1.3", 3)]
    assert move(three, "before", two).json()["order"] == 1
    assert titles(revision) == [("Clip 1.3", 1), ("Clip 1.2", 2), ("Clip 1.1", 3)]
    stranger = Clip.objects.get(revision__chapter__number=2, order=1)
    assert move(one, "before", stranger).json() == {
        "target": ["Not a clip of the same revision (or it is in the bin)."]
    }
    assert "target" in move(one, "after", one).json() and "target" in move(one, "before").json()
    assert events("course.moved").count() == 4
    # cards and quiz items: the same four ways within their chapter
    chapter = Chapter.objects.get(number=1)
    extra = QuizItem.objects.create(chapter=chapter, kind="true_false", text="Second", answer="false")
    assert extra.order == 2  # a new item goes last
    assert client.post(f"{COURSE}items/{extra.pk}/move/", {"to": "first"}, format="json").status_code == 200
    assert list(QuizItem.objects.filter(chapter=chapter).values_list("text", "order")) == [
        ("Second", 1),
        ("Statement 1", 2),
    ]
    card = FlashCard.objects.create(chapter=chapter, order=2, front="Back side", back="b")
    assert client.post(f"{COURSE}cards/{card.pk}/move/", {"to": "first"}, format="json").status_code == 200
    assert list(FlashCard.objects.filter(chapter=chapter).values_list("front", "order")) == [
        ("Back side", 1),
        ("Front 1", 2),
    ]


def test_a_revision_is_reviewed_by_another_person_and_published_now_or_once_at_its_time(editor, reviewer, physics):
    revision = Revision.objects.get(chapter__number=1)
    Revision.objects.filter(pk=revision.pk).update(status="draft")
    editing, reviewing = signed_in(editor), signed_in(reviewer)
    url = f"{COURSE}revisions/{revision.pk}/"
    assert editing.get(url).json()["transitions"] == ["submit"]
    assert editing.post(url + "submit/").json()["status"] == "review"
    item = InboxItem.objects.get(kind="review", target_type="learn.revision", done_at=None)
    assert (item.permission, item.data) == ("staff.publish_course", {"subject": "PHY"})
    assert editing.post(url + "approve/").status_code == 403  # an editor approves nothing
    assert reviewing.get(url).json()["transitions"] == ["approve", "needs_changes", "publish", "unpublish"]
    # sent back with what to change: back to draft, the submitter's inbox
    assert reviewing.post(url + "needs-changes/", {}, format="json").json() == {"comment": ["Say what to change."]}
    assert reviewing.post(url + "needs-changes/", {"comment": "Clip 2 is too long"}, format="json").status_code == 200
    asked = InboxItem.objects.get(kind="review", done_at=None)
    assert asked.assignee == editor and asked.title.startswith("Changes asked")
    assert InboxItem.objects.get(pk=item.pk).done_at is not None
    editing.post(url + "submit/")
    # whoever submitted it never approves or publishes it (an owner neither)
    owner = make_staff(roles.OWNER)
    Revision.objects.filter(pk=revision.pk).update(submitted_by=owner)
    refused = signed_in(owner).post(url + "approve/")
    assert refused.status_code == 403 and refused.json()["code"] == "own_edit"
    # approved, then published at a time to come, by the task, once
    assert reviewing.post(url + "approve/", {"comment": "Fine"}, format="json").json()["status"] == "approved"
    past = timezone.now() - timedelta(minutes=1)
    assert "publish_at" in reviewing.post(url + "publish/", {"publish_at": past.isoformat()}, format="json").json()
    at = timezone.now() + timedelta(hours=2)
    answer = reviewing.post(url + "publish/", {"publish_at": at.isoformat()}, format="json").json()
    assert answer["status"] == "approved" and answer["publish_at"] and answer["reviewer"]["id"] == reviewer.pk
    assert course.publish_due() == 0  # not yet
    assert course.publish_due(now=at + timedelta(minutes=1)) == 1
    assert course.publish_due(now=at + timedelta(minutes=6)) == 0  # once
    revision.refresh_from_db()
    assert (revision.status, revision.publish_at) == ("published", None)
    published = events("course.revision_published").get()
    assert published.actor_type == "system" and published.details["approved_by"] == reviewer.pk
    # published now needs a ready clip; back to draft from anywhere (students keep their progress)
    assert reviewing.post(url + "unpublish/").json()["status"] == "draft"
    editing.post(url + "submit/")
    Clip.objects.filter(revision=revision).update(processing="failed")
    assert reviewing.post(url + "publish/").json() == {
        "non_field_errors": ["None of its clips is ready yet: it would publish nothing to watch."]
    }


def test_a_scheduled_publish_without_a_ready_clip_waits_in_the_inbox(reviewer, physics):
    revision = Revision.objects.get(chapter__number=2)
    at = timezone.now() + timedelta(minutes=10)
    Revision.objects.filter(pk=revision.pk).update(status="approved", publish_at=at, reviewer=reviewer)
    Clip.objects.filter(revision=revision).update(processing="processing")
    assert course.publish_due(now=at) == 0
    waiting = InboxItem.objects.get(kind="failed_job", target_type="learn.revision", done_at=None)
    assert waiting.title.startswith("Scheduled publish waits")
    Clip.objects.filter(revision=revision).update(processing="ready")
    assert course.publish_due(now=at) == 1 and InboxItem.objects.get(pk=waiting.pk).done_at is not None


def stored(name, content=b"x"):
    return default_storage.save(name, ContentFile(content))


def test_the_bin_restores_within_30_days_and_the_purge_takes_a_clips_files_only_after(
    editor, physics, django_capture_on_commit_callbacks
):
    revision = Revision.objects.get(chapter__number=1)
    clip = Clip.objects.get(revision=revision, order=2)
    master = stored(f"learn/hls/{clip.pk}/v1/master.m3u8")
    segment = stored(f"learn/hls/{clip.pk}/v1/480p/seg_000.ts")
    clip.hls_path, clip.source = master, stored("learn/sources/clip.mp4")
    clip.save()
    client = signed_in(editor)
    gone = client.delete(f"{COURSE}clips/{clip.pk}/").json()
    assert gone["kind"] == "clips" and gone["bin_until"] and gone["chapter"]["subject"] == "PHY"
    assert titles(revision) == [("Clip 1.1", 1), ("Clip 1.3", 2)]  # the rest numbered again
    assert client.delete(f"{COURSE}clips/{clip.pk}/").status_code == 404  # outside the live rows now
    binned = client.get(f"{COURSE}bin/?kind=clips").json()["results"]
    assert [row["id"] for row in binned] == [clip.pk]
    assert client.get(f"{COURSE}clips/{clip.pk}/").json()["deleted_at"]  # its record still opens
    assert client.post(f"{COURSE}clips/{clip.pk}/restore/").status_code == 200
    assert titles(revision) == [("Clip 1.1", 1), ("Clip 1.2", 2), ("Clip 1.3", 3)]  # back at its place
    assert client.post(f"{COURSE}clips/{clip.pk}/restore/").json() == {
        "non_field_errors": ["This clip is not in the bin."]
    }
    client.delete(f"{COURSE}clips/{clip.pk}/")
    deleted_at = Clip.all_objects.get(pk=clip.pk).deleted_at
    with django_capture_on_commit_callbacks(execute=True):
        assert course.purge(now=deleted_at + timedelta(days=29)) == {"clips": 0, "cards": 0, "items": 0}
    assert all(default_storage.exists(name) for name in (master, segment, clip.source.name))  # kept 30 days
    assert Clip.all_objects.filter(pk=clip.pk).exists()
    Clip.all_objects.filter(pk=clip.pk).update(deleted_at=timezone.now() - timedelta(days=30, seconds=1))
    assert client.post(f"{COURSE}clips/{clip.pk}/restore/").json()["non_field_errors"][0].startswith("It was in")
    with django_capture_on_commit_callbacks(execute=True):
        assert course.purge()["clips"] == 1
    assert not Clip.all_objects.filter(pk=clip.pk).exists()
    assert not any(default_storage.exists(name) for name in (master, segment, clip.source.name))
    assert events("course.purged").get().details["deleted"]["clips"] == 1


def test_the_bin_is_hidden_from_the_apps_and_the_websites_api(physics):
    api = APIClient()
    user = sign_in(api, student())
    Entitlement.objects.create(user=user, subject=physics)
    first = Clip.objects.get(revision__chapter__number=1, order=1)
    item, card = QuizItem.objects.get(chapter__number=1), FlashCard.objects.get(chapter__number=1)
    Progress.objects.create(user=user, clip=first, seconds_watched=120, completed=True)
    QuizAttempt.objects.create(user=user, item=item, correct=False, created=timezone.now() - timedelta(days=2))
    CardReview.objects.create(user=user, card=card, known=False, created=timezone.now() - timedelta(days=2))
    for row in (first, item, card):
        course.delete(row)
    chapters = api.get("/api/v1/learn/chapters/", {"subject": physics.pk}).json()["results"]
    assert (chapters[0]["clips"], chapters[0]["minutes"], chapters[0]["progress"]) == (2, 4, 0)
    second = Clip.objects.get(revision__chapter__number=1, order=1)  # renumbered: the first now
    assert chapters[0]["free_preview"] == second.pk
    detail = api.get(f"/api/v1/learn/chapters/{chapters[0]['id']}/").json()
    assert [clip["title"] for clip in detail["revision"]["clips"]] == ["Clip 1.2", "Clip 1.3"]
    assert (detail["flash_cards"], detail["quiz_items"]) == (0, 0)
    assert api.get(f"/api/v1/learn/clips/{first.pk}/").status_code == 404
    assert api.get("/api/v1/learn/quiz/", {"chapter": chapters[0]["id"]}).json()["results"] == []
    assert api.get("/api/v1/learn/flash-cards/", {"chapter": chapters[0]["id"]}).json()["results"] == []
    assert api.get("/api/v1/learn/revise-again/").json() == {"quiz_items": [], "flash_cards": []}
    plan = api.get("/api/v1/learn/plan/", {"exam_date": str(timezone.localdate() + timedelta(days=30))}).json()
    assert first.pk not in [clip["id"] for day in plan["days"] for clip in day["clips"]]
    learning = api.get("/api/v1/me/learning/").json()["subjects"][0]
    assert (learning["clips_total"], learning["clips_watched"], learning["quiz_answers"]) == (5, 0, 0)
    # restored: everything as before
    course.restore(Clip.all_objects.get(pk=first.pk))
    learning = api.get("/api/v1/me/learning/").json()["subjects"][0]
    assert (learning["clips_total"], learning["clips_watched"]) == (6, 1)


def test_a_failed_clip_says_why_in_words_and_is_retried(editor, physics, monkeypatch):
    queued = []
    monkeypatch.setattr("learn.tasks.process_clip.delay", queued.append)
    clip = Clip.objects.get(revision__chapter__number=1, order=1)
    Clip.objects.filter(pk=clip.pk).update(
        processing="failed", processing_error=f"{media.NOT_A_CLIP} (video: mpeg4)", source=stored("learn/sources/a.avi")
    )
    client = signed_in(editor)
    record = client.get(f"{COURSE}clips/{clip.pk}/").json()
    assert record["reason"].startswith("The file is not a video we take") and record["can_retry"] is True
    assert record["error_detail"].endswith("(video: mpeg4)") and record["player_url"] is None
    retried = client.post(f"{COURSE}clips/{clip.pk}/retry/")
    assert retried.status_code == 200 and retried.json()["processing"] == "processing"
    assert client.post(f"{COURSE}clips/{clip.pk}/retry/").json() == {
        "non_field_errors": ["It is being processed: nothing to retry."]
    }
    assert events("course.clip_retried").count() == 1
    Clip.objects.filter(pk=clip.pk).update(modified=timezone.now() - timedelta(hours=2))  # stuck: its task lost
    assert client.get(f"{COURSE}clips/{clip.pk}/").json()["reason"].startswith("It has been processing for over")
    ready = client.get(f"{COURSE}clips/{Clip.objects.get(revision__chapter__number=1, order=2).pk}/").json()
    assert ready["poster_url"].startswith("/learn/hls/") and ready["player_url"].startswith("/learn/preview/")
    assert ready["reason"] == "" and ready["can_retry"] is False
    changed = client.patch(f"{COURSE}clips/{clip.pk}/", {"title": "Ohm", "is_free_preview": True, "tags": ["ohm"]},
                           format="json").json()  # fmt: skip
    assert (changed["title"], changed["is_free_preview"], changed["tags"]) == ("Ohm", True, ["ohm"])
    assert events("course.clip_changed").get().changes["tags"] == [[], ["ohm"]]


def stat(item, n, p=None, discrimination=None, flags=()):
    return ItemStat.objects.create(item=item, n=n, p=p, discrimination=discrimination, flags=list(flags))


def test_the_bank_shows_the_statistics_with_na_under_30_learners_and_filters_by_them(editor, physics):
    small, large = QuizItem.objects.order_by("chapter__number")
    stat(small, 12, p=0.5, discrimination=0.3)
    stat(large, 40, p=0.97, discrimination=0.2, flags=["too_easy"])
    QuizItem.objects.filter(pk=large.pk).update(difficulty="easy", topic="Ohm's law")
    client = signed_in(editor)
    rows = {row["id"]: row for row in client.get(f"{COURSE}items/").json()["results"]}
    assert rows[small.pk]["stats"] | {"computed_at": None} == {
        "n": 12, "p": None, "discrimination": None, "flags": [], "computed_at": None, "n_too_small": True,
    }  # fmt: skip
    assert (rows[large.pk]["stats"]["p"], rows[large.pk]["stats"]["flags"]) == (0.97, ["too_easy"])
    assert rows[large.pk]["source"] is None and rows[large.pk]["chapter"]["subject"] == "PHY"

    def ids(query):
        return [row["id"] for row in client.get(f"{COURSE}items/?{query}").json()["results"]]

    assert ids("flags=any") == ids("flags=too_easy") == [large.pk]
    assert ids("flags=too_hard") == [] and ids("n_too_small=true") == [small.pk]
    assert ids("difficulty=none") == [small.pk] and ids("difficulty=easy") == [large.pk]
    assert ids("topic=ohm") == [large.pk] and ids("source=app") == [small.pk, large.pk]
    assert ids("q=statement%202") == [large.pk] and ids("source=book") == []


def test_an_item_is_changed_as_the_admin_checks_it_and_keeps_its_history(editor, physics):
    item = QuizItem.objects.get(chapter__number=1)
    client = signed_in(editor)
    url = f"{COURSE}items/{item.pk}/"
    refused = client.patch(url, {"kind": "mcq", "options": ["(i) a", "(ii) b"], "answer": "3"}, format="json")
    assert refused.json() == {"answer": ["The number of one of the options."]}
    body = {"kind": "mcq", "options": ["(i) a", "(ii) b"], "answer": "2", "difficulty": "hard", "bloom": "apply",
            "marks": 1, "topic": "Charges", "tags": ["coulomb"]}  # fmt: skip
    changed = client.patch(url, body, format="json").json()
    assert (changed["kind"], changed["answer"], changed["difficulty"], changed["tags"]) == ("mcq", "2", "hard",
                                                                                          ["coulomb"])  # fmt: skip
    versions = client.get(url + "history/").json()
    assert versions[0]["type"] == "~" and {change["field"] for change in versions[0]["changes"]} >= {"kind", "answer"}
    assert client.patch(url, {"bloom": "remembering"}, format="json").status_code == 400


def test_needs_checking_files_one_open_report_in_the_content_triage(editor, physics):
    item = QuizItem.objects.get(chapter__number=2)
    stat(item, 40, p=0.2, discrimination=0.05, flags=["low_discrimination"])
    client = signed_in(editor)
    first = client.post(f"{COURSE}items/{item.pk}/flag/", {"note": "The key looks wrong"}, format="json")
    assert first.status_code == 201
    report = ErrorReport.objects.get(pk=first.json()["report"])
    assert (report.category, report.target_id, report.subject.code) == ("item_analysis", item.pk, "PHY")
    assert report.note.startswith("The key looks wrong") and "40 learners" in report.note
    assert InboxItem.objects.get(kind="error_report", done_at=None).data == {"subject": "PHY"}
    again = client.post(f"{COURSE}items/{item.pk}/flag/", {}, format="json")
    assert again.status_code == 200 and again.json() == {"report": report.pk, "created": False}
    assert ErrorReport.objects.count() == 1
    assert client.get(f"{COURSE}items/?flagged=true").json()["results"][0]["flagged"] == report.pk
    ErrorReport.objects.filter(pk=report.pk).update(state="rejected")
    assert client.post(f"{COURSE}items/{item.pk}/flag/", {}, format="json").status_code == 201  # closed: a new one


def test_the_banks_bulk_metadata_is_a_job_with_a_dry_run_first(editor, physics, django_capture_on_commit_callbacks):
    other = QuizItem.objects.get(chapter__subject=chemistry())
    mine = list(QuizItem.objects.filter(chapter__subject=physics).values_list("pk", flat=True))
    client = signed_in(editor)
    body = {"kind": "bulk_action", "dry_run": True, "params": {"action": "item_metadata", "targets": [*mine, other.pk],
            "payload": {"difficulty": "hard", "tags_add": ["revise"]}, "reason": "Tagging the hard ones"}}  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True):
        dry = client.post(f"{STAFF}jobs/", body, format="json").json()
    job = Job.objects.get(pk=dry["id"])
    assert job.state == "done" and job.result["outcomes"] == {"valid": 2, "refused": 1}
    assert job.errors[0]["id"] == other.pk  # another subject's: out of reach
    assert not QuizItem.objects.filter(difficulty="hard").exists()  # a dry run changes nothing
    body["dry_run"], body["params"]["targets"] = False, mine
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"{STAFF}jobs/", body, format="json")
    assert set(QuizItem.objects.filter(difficulty="hard").values_list("pk", flat=True)) == set(mine)
    assert all("revise" in item.tags.names() for item in QuizItem.objects.filter(pk__in=mine))
    assert events("item_metadata.executed").count() == 2


def test_the_lists_read_with_a_fixed_number_of_queries(physics):
    client = signed_in(make_staff(roles.OWNER))
    paths = [
        "subjects/",
        f"subjects/{physics.pk}/outline/",
        "items/",
        "bin/?kind=clips",
        "bin/?kind=items",
    ]
    one = {path: queries(client, COURSE + path) for path in paths}
    for number in (3, 4, 5):
        chapter = Chapter.objects.create(subject=physics, number=number, title=f"Chapter {number}", weight=5)
        revision = Revision.objects.create(chapter=chapter, title=f"R {number}", status="published")
        for order in (1, 2):
            clip = Clip.objects.create(revision=revision, order=order, title="c", processing="ready", duration=60)
            course.delete(clip) if order == 2 else None
        item = QuizItem.objects.create(chapter=chapter, kind="true_false", text="t", answer="true")
        stat(item, 31, p=0.5, discrimination=0.2)
        course.delete(QuizItem.objects.create(chapter=chapter, kind="true_false", text="u", answer="true"))
        FlashCard.objects.create(chapter=chapter, front="f", back="b")
    for path in paths:
        assert queries(client, COURSE + path) == one[path], path
