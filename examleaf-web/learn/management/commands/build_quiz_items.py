import re
from collections import Counter

from django.core.management.base import BaseCommand

from content.models import Question
from learn.models import Chapter, QuizItem

ANSWER = re.compile(r"^\*\*Ans\.?\*\*\s*(.+?)\s*\*\(1\)\*$", re.S)  # **Ans.** (iii) much stronger *(1)*
ROMAN = ["i", "ii", "iii", "iv", "v", "vi"]
LABEL = re.compile(r"\((\w+)\)")
CHAPTER = re.compile(r"^Ch (\d+): ")


def parse(question):
    """(kind, options, answer, explanation) of a one-mark question whose options and answer parse unambiguously, or
    (None, why not)."""
    found = ANSWER.match(question.solution.body_md.strip())
    if not found:
        return None, "answer not on one line"
    answer, _, explanation = found.group(1).partition(" — ")
    answer, text = answer.strip(), question.text_md
    if question.options_json:
        labels = [LABEL.match(option) for option in question.options_json]
        picked = LABEL.match(answer)
        if not all(labels) or [label.group(1) for label in labels] != ROMAN[: len(labels)]:
            return None, "options not (i), (ii) …"
        if not picked or picked.group(1) not in ROMAN[: len(labels)] or len(LABEL.findall(answer)) > 1:
            return None, "not one option"
        return ("mcq", question.options_json, str(ROMAN.index(picked.group(1)) + 1), explanation), None
    if re.search(r"true or false", text, re.I):
        verdict = re.match(r"(True|False)\b[\s.,:;—–-]*(.*)", answer, re.S)
        if not verdict:
            return None, "not true or false"
        return ("true_false", [], verdict.group(1).lower(), verdict.group(2) or explanation), None
    if len(re.findall(r"_{3,}", text)) == 1:
        words = LABEL.sub("", answer).strip(" .")
        if not words or "$" in answer or len(words.split()) > 3 or re.search(r"[;,/]| or | and ", words):
            return None, "blank's answer not a short word"
        return ("fill_blank", [], "|".join([words, *LABEL.findall(answer)]), explanation), None
    return None, "not an objective question"


class Command(BaseCommand):
    help = (
        "Make quiz items (multiple choice, true or false, fill in the blank) from the imported one-mark questions "
        "whose options and answer parse unambiguously; the others are skipped. Items made before are kept as they "
        "are (editors may have changed them). Run import_chapter_insights first: items go to its chapters."
    )

    def handle(self, **options):
        chapters = {(c.subject_id, c.number): c for c in Chapter.objects.all()}
        made, skipped = Counter(), Counter()
        questions = Question.objects.filter(marks_text="1", solution__isnull=False)
        for question in questions.select_related("solution", "paper__book__subject").prefetch_related("tags"):
            code = question.paper.book.subject.code
            numbers = {int(m.group(1)) for tag in question.tags.all() if (m := CHAPTER.match(tag.name))}
            chapter = chapters.get((question.paper.book.subject_id, numbers.pop())) if len(numbers) == 1 else None
            item, why = parse(question) if chapter else (None, "no single chapter")
            if item is None:
                skipped[code, why] += 1
                continue
            kind, choices, answer, explanation = item
            _, new = QuizItem.all_objects.get_or_create(  # one in the course's bin stays there: kept, not made again
                source=question,
                defaults=dict(chapter=chapter, kind=kind, text=question.text_md, options=choices, answer=answer,
                              explanation=explanation.strip()),
            )  # fmt: skip
            made[code, "new" if new else "kept"] += 1
        for code in sorted({code for code, _ in made | skipped}):
            reasons = ", ".join(f"{why} {n}" for (c, why), n in sorted(skipped.items()) if c == code)
            self.stdout.write(
                f"{code}: {made[code, 'new']} new, {made[code, 'kept']} kept; skipped {reasons or 'none'}"
            )
