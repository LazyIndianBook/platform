"""Journeys that must keep the visitor's destination: signup and code log-in from the QR landing page."""
import re
from django.core import mail
from django.test import Client, override_settings
from django.test.utils import setup_test_environment
setup_test_environment()
override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"]).enable()
from content.models import Board

def chain(client, response, limit=8):
    out = []
    while response.status_code in (301, 302) and limit:
        out.append(f"{response.status_code} -> {response['Location']}")
        response = client.get(response["Location"])
        limit -= 1
    out.append(f"{response.status_code} (final page)")
    return out, response

def code_from_mail():
    body = mail.outbox[-1].body
    m = re.search(r"\b(\d{6})\b", body)
    return m.group(1) if m else None

NEXT = "/s/PHY-E01/"
c = Client(raise_request_exception=False)
board = Board.objects.first()
print("1) signup from the QR landing page, next =", NEXT)
r = c.get(f"/account/signup/?next={NEXT}")
print("   signup form carries next:", f'value="{NEXT}"' in r.content.decode())
data = {"full_name": "Flow Tester", "email": "flow-tester@example.com", "password1": "Tigris-Brahmaputra-2027", "password2": "Tigris-Brahmaputra-2027",
        "class_level": 12, "board": board.pk, "district": "Kamrup", "date_of_birth": "2000-01-01", "consent": "on", "next": NEXT}
r = c.post("/account/signup/", data)
print("   POST signup:", r.status_code, r.get("Location"))
steps, page = chain(c, r)
print("   ", " | ".join(steps))
print("    outbox:", [m.subject for m in mail.outbox])
if mail.outbox:
    code = code_from_mail()
    print("    code found in the email:", bool(code))
    html = page.content.decode()
    action = re.search(r'<form[^>]*method="post"[^>]*action="([^"]*)"', html)
    print("    confirm page title:", re.search(r"<title>(.*?)</title>", html, flags=re.S).group(1).strip(), "| action", action.group(1) if action else None, "| next in form:", f'value="{NEXT}"' in html or "next" in html)
    r = c.post(page.request["PATH_INFO"] if hasattr(page, "request") else "/account/confirm-email/", {"code": code, "next": NEXT})
    print("    POST confirm:", r.status_code, r.get("Location"))
    steps, page = chain(c, r)
    print("   ", " | ".join(steps))

print()
print("2) log in with an emailed code from the QR landing page, next =", NEXT)
c2 = Client(raise_request_exception=False)
mail.outbox.clear()
r = c2.post("/account/login/code/", {"email": "flow-tester@example.com", "next": NEXT})
print("   POST request code:", r.status_code, r.get("Location"))
steps, page = chain(c2, r)
print("   ", " | ".join(steps))
print("    outbox:", [m.subject for m in mail.outbox])
if mail.outbox:
    code = code_from_mail()
    r = c2.post("/account/login/code/confirm/", {"code": code, "next": NEXT})
    print("    POST confirm:", r.status_code, r.get("Location"))
    steps, page = chain(c2, r)
    print("   ", " | ".join(steps))

print()
print("3) password log in from the landing page, next =", NEXT)
c3 = Client(raise_request_exception=False)
r = c3.post("/account/login/", {"login": "flow-tester@example.com", "password": "Tigris-Brahmaputra-2027", "next": NEXT})
print("   POST login:", r.status_code, r.get("Location"))
steps, page = chain(c3, r)
print("   ", " | ".join(steps))

print()
print("4) a visitor who logs in with no next (header 'Log in') lands on:")
c4 = Client(raise_request_exception=False)
r = c4.post("/account/login/", {"login": "flow-tester@example.com", "password": "Tigris-Brahmaputra-2027"})
print("   ", r.status_code, r.get("Location"))

print()
print("5) logged-out visitor on /account/record/ -> login -> back?")
c5 = Client(raise_request_exception=False)
r = c5.get("/account/record/")
print("   ", r.status_code, r.get("Location"))
r = c5.post(r["Location"].split("?")[0], {"login": "flow-tester@example.com", "password": "Tigris-Brahmaputra-2027", "next": "/account/record/"})
print("   ", r.status_code, r.get("Location"))

print()
print("6) a student saves marks from the solutions page: where does the form send them?")
from content.models import Paper
c3.get("/s/PHY-E01/")
r = c3.post("/account/record/add/PHY-E01/", {"date": "2026-10-08", "marks_obtained": "55", "time_taken_minutes": "170", "notes": ""})
print("   valid save:", r.status_code, r.get("Location"))
r = c3.post("/account/record/add/PHY-E01/", {"date": "2026-10-08", "marks_obtained": "955", "notes": ""})
print("   invalid save: status", r.status_code, "template", [t.name for t in r.templates][:1], "(a separate page, not the solutions page)")
