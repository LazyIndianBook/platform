"""Redesign stage 2a: every email gets an HTML part made from its text, and keeps its own if it has one."""

import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives

from ops import tasks

pytestmark = pytest.mark.django_db


def test_every_email_gets_an_html_part_made_from_its_text(mailoutbox):
    text = "Hello <b>!\n\n483920\n\nhttps://examleaf.in/c/x.y/"
    tasks.queue_email(EmailMessage("[ExamLeaf] Your code", text, to=["a@example.com"]))
    message = mailoutbox[-1]
    html, mimetype = message.alternatives[0]
    assert message.body == text and mimetype == "text/html"
    assert ">Your code</h1>" in html and "Hello &lt;b&gt;!" in html and "<b>" not in html
    assert 'color: #0B2A5B">483920</p>' in html and '<a href="https://examleaf.in/c/x.y/"' in html
    own = EmailMultiAlternatives("Hi", "text", to=["a@example.com"])
    own.attach_alternative("<p>mine</p>", "text/html")
    tasks.queue_email(own)
    assert mailoutbox[-1].alternatives == [("<p>mine</p>", "text/html")]
