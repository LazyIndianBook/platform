// What the console's tests need from the Django backend beyond HTTP: staff members to sign in with (a role group, a
// confirmed email address, a password and an authenticator app with a known secret), the records the real-backend
// journey works on (a customer with an order paid online, an erasure request, an incident; a paper whose solution is
// drafted and published), all made and deleted
// through manage.py shell, and the authenticator's codes (RFC 6238, as allauth checks them).
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import path from "node:path";

import { djangoDir, djangoEnv } from "../playwright.config";

const python = process.env.DJANGO_PYTHON ?? path.join(djangoDir, ".venv/bin/python");

function shell(code: string): string {
  return execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: djangoDir,
    env: { ...process.env, ...djangoEnv },
    stdio: "pipe",
  }).toString();
}

/** The last line a shell snippet printed, as JSON. */
const lastJson = <T>(output: string): T => JSON.parse(output.trim().split("\n").pop()!) as T;

const py = (value: string) => JSON.stringify(value);

export type Staff = { email: string; password: string; secret: string; name: string };

/** A base32 secret of 32 letters, as an authenticator app keeps it. */
export function newSecret(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  return Array.from({ length: 32 }, () => alphabet[Math.floor(Math.random() * 32)]).join("");
}

/** A member of staff with the role group (ADMIN by default) and an authenticator app; answers their id. A role of
 *  STAFF_PASSKEY_ROLES (OWNER, ADMIN, FINANCE) gets a passkey's row too, as the staff API asks of them first (never
 *  used to sign in here: the tests sign in with the authenticator's code). */
export function createStaff(staff: Staff, role = "ADMIN"): number {
  return lastJson<number>(
    shell(`
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import TOTP
from django.contrib.auth.models import Group
from accounts.models import User
User.objects.filter(email=${py(staff.email)}).delete()
user = User.objects.create_user(${py(staff.email)}, ${py(staff.password)}, full_name=${py(staff.name)}, is_staff=True)
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
user.groups.add(Group.objects.get(name=${py(role)}))
TOTP.activate(user, ${py(staff.secret)})
if ${py(role)} in ("OWNER", "ADMIN", "FINANCE"):
    Authenticator.objects.create(user=user, type=Authenticator.Type.WEBAUTHN, data={"name": "E2E security key"})
print(user.pk)
`),
  );
}

/** Deletes the members of staff the tests made (their emails start with "admin-ui-"), and first the change requests
 *  they asked for or decided (which keep their people: PROTECT) with their inbox items. */
export function deleteStaff(emails: string[]) {
  shell(`
from django.db.models import Q
from accounts.models import User
from staff.models import ChangeRequest, InboxItem
users = User.objects.filter(email__in=${JSON.stringify(emails)}, email__startswith="admin-ui-")
requests = ChangeRequest.objects.filter(Q(maker__in=users) | Q(approvals__user__in=users)).distinct()
InboxItem.objects.filter(target_type="staff.changerequest", target_id__in=[str(pk) for pk in requests.values_list("pk", flat=True)]).delete()
ChangeRequest.objects.filter(pk__in=list(requests.values_list("pk", flat=True))).delete()
print(users.delete())
`);
}

export type RealWorld = { customer: number; email: string; order: string; request: number; incident: number };

/** For the real-backend journey: an adult customer with a confirmed address and a mobile number, an order of ₹1,500
 *  paid online (a captured Razorpay payment, not shipped: a refund cancels it, above SUPPORT's ₹1,000), the customer's
 *  erasure request (its inbox item follows) and an incident. */
export function seedRealWorld(stamp: number): RealWorld {
  return lastJson<RealWorld>(
    shell(`
import json
from datetime import date
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import User
from shop.models import Order, Payment
from staff.models import DataRequest, Incident
email = ${py(`admin-ui-customer-${stamp}@example.com`)}
user = User.objects.create_user(email, "Customer-e2e-2026!", full_name="Real E2E Customer", class_level=12, date_of_birth=date(2000, 1, 1), consent_at=timezone.now(), phone="+919864012345")
EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
address = {"name": "Real E2E Customer", "phone": "+919864012345", "line1": "1 Test Lane", "line2": "", "city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"}
order = Order.objects.create(user=user, email=email, shipping_address=address, subtotal=1500, total=1500, payment_method="razorpay", placed_at=timezone.now())
Order.objects.filter(pk=order.pk).update(status="paid")
payment = Payment.objects.create(order=order, method="razorpay", amount=1500, razorpay_order_id=${py(`order_e2e${stamp}`)}, razorpay_payment_id=${py(`pay_e2e${stamp}`)})
Payment.objects.filter(pk=payment.pk).update(status="captured")
request = DataRequest.objects.create(kind="erasure", channel="email", user=user, requester=email, summary="Please erase my account and what you hold about me.")
incident = Incident.objects.create(title=${py(`E2E incident ${stamp}`)}, kind="other", detected_at=timezone.now(), description="Made by the console's tests.")
order.refresh_from_db()
print(json.dumps({"customer": user.pk, "email": email, "order": order.number, "request": request.pk, "incident": incident.pk}))
`),
  );
}

export type RealTicket = { number: string; id: number };

/** For the support journey: the customer's complaint about their order, made as the contact form makes one (its
 *  number, its clocks, the acknowledgement by email). */
export function seedTicket(world: RealWorld): RealTicket {
  return lastJson<RealTicket>(
    shell(`
import json
from accounts.models import User
from support import services
from support.models import Ticket, TicketMessage
user = User.objects.get(pk=${world.customer})
ticket = services.create_ticket(source=Ticket.Source.FORM, channel=TicketMessage.Channel.WEB, subject="The parcel has not come (e2e)", body="Order ${world.order} has not come yet.", user=user, name=user.full_name, email=user.email, category="order", order=user.orders.get(number=${py(world.order)}))
print(json.dumps({"number": ticket.number, "id": ticket.pk}))
`),
  );
}

/** Deletes what seedRealWorld made and what the journey made of it but the change requests (deleteStaff takes those)
 *  and the audit events (the log is append-only). */
export function deleteRealWorld(world: RealWorld) {
  shell(`
from accounts.models import User
from shop.models import Order, Payment
from staff.models import DataRequest, InboxItem, Incident, StaffInvite
from support.models import Ticket
tickets = Ticket.objects.filter(user_id=${world.customer})
InboxItem.objects.filter(target_type="support.ticket", target_id__in=[str(pk) for pk in tickets.values_list("pk", flat=True)]).delete()
tickets.delete()
orders = Order.objects.filter(number=${py(world.order)})
Payment.objects.filter(order__in=orders).delete()
orders.delete()
InboxItem.objects.filter(target_type="staff.datarequest", target_id=${py(String(world.request))}).delete()
DataRequest.objects.filter(pk=${world.request}).delete()
InboxItem.objects.filter(target_type="staff.incident", target_id=${py(String(world.incident))}).delete()
Incident.objects.filter(pk=${world.incident}).delete()
StaffInvite.objects.filter(email__startswith="admin-ui-").delete()
print(User.objects.filter(pk=${world.customer}).delete())
`);
}

export type OrdersWorld = { title: string; order: string; school: string };

/** For the Orders journey: three books on sale (₹800, ₹900, ₹1,000, 50 copies each), and an order of one copy of
 *  each, paid online and sent, for a partial refund (two books: ₹1,900, above SUPPORT's ₹1,000). `school` is the
 *  address the staff order of the journey goes to. */
export function seedOrdersWorld(stamp: number): OrdersWorld {
  return lastJson<OrdersWorld>(
    shell(`
import json
from decimal import Decimal
from django.utils import timezone
from shop.models import Order, OrderItem, Payment, Product, Shipment
title = ${py(`E2E Physics ${stamp}`)}
books = [
    Product.objects.create(title=f"{title} {n}", slug=f"e2e-physics-${stamp}-{n}", kind="sample-papers", mrp=Decimal(price) + 100, price=Decimal(price), stock=50, weight_grams=300)
    for n, price in enumerate(["800", "900", "1000"], start=1)
]
address = {"name": "Real E2E Buyer", "phone": "+919864012345", "line1": "1 Test Lane", "line2": "", "city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"}
order = Order.objects.create(email=${py(`admin-ui-buyer-${stamp}@example.com`)}, shipping_address=address, subtotal=2700, total=2700, payment_method="razorpay", placed_at=timezone.now())
for book in books:
    OrderItem.objects.create(order=order, product=book, title=book.title, hsn_code="4901", gst_rate=Decimal("0"), mrp=book.mrp.amount, unit_price=book.price.amount, quantity=1, discount=Decimal("0"))
Order.objects.filter(pk=order.pk).update(status="shipped")
payment = Payment.objects.create(order=order, method="razorpay", amount=2700, razorpay_order_id=${py(`order_e2eo${stamp}`)}, razorpay_payment_id=${py(`pay_e2eo${stamp}`)})
Payment.objects.filter(pk=payment.pk).update(status="captured")
Shipment.objects.create(order=order, courier="India Post", tracking_number=${py(`EA${String(stamp).slice(-9)}IN`)})
order.refresh_from_db()
print(json.dumps({"title": title, "order": order.number, "school": ${py(`admin-ui-school-${stamp}@example.com`)}}))
`),
  );
}

export type ContentWorld = { book: number; paper: number; code: string; solution: number };

/** For the content journey: a book and a paper of the run's own (PHY-T<5 digits>), its question 1(a) with a solution
 *  as published, which an editor drafts and a reviewer publishes. */
export function seedContent(stamp: number): ContentWorld {
  return lastJson<ContentWorld>(
    shell(`
import json
from content.models import Board, Book, ClassLevel, Paper, Question, Solution, Subject
board, _ = Board.objects.get_or_create(short_name="ASSEB", defaults={"name": "Assam State School Education Board", "state": "Assam"})
level, _ = ClassLevel.objects.get_or_create(number=12)
subject, _ = Subject.objects.get_or_create(board=board, class_level=level, code="PHY", defaults={"name": "Physics"})
book = Book.objects.create(slug=${py(`e2e-physics-${stamp}`)}, title="Physics, the console's tests", subject=subject, edition="E2E")
code = ${py(`PHY-T${String(stamp).slice(-5)}`)}
paper = Paper.objects.create(book=book, code=code, tier="E", number=1, title="The console's test paper", full_marks=70, pass_marks=21, time_text="3 hours")
question = Question.objects.create(paper=paper, order=1, label="1(a)", marks_text="2", text_md="A cell of emf 6 V and internal resistance 1 ohm drives 11 ohm. Find the current.")
solution = Solution.objects.create(question=question, body_md=${py("$I = \\dfrac{6}{12} = 5$ A")})
print(json.dumps({"book": book.pk, "paper": paper.pk, "code": code, "solution": solution.pk}))
`),
  );
}

/** Deletes what seedOrdersWorld made, and the staff order the journey made for `school` (change requests: deleteStaff;
 *  audit events stay: the log is append-only). */
export function deleteOrdersWorld(world: OrdersWorld) {
  shell(`
from shop.models import Order, Payment, Product
orders = Order.objects.filter(email__in=[${py(world.school)}]) | Order.objects.filter(number=${py(world.order)})
Payment.objects.filter(order__in=orders).delete()
orders.delete()
print(Product.objects.filter(title__startswith=${py(world.title)}).delete())
`);
}

export type FinanceWorld = { order: string; payment: number; request: number };

/** For the Finance journey: an order of ₹2,400 paid online with live keys and not yet sent (with no keys the site
 *  counts as live, and Finance leaves test orders out), and its refund asked for by `maker` (a SUPPORT member: above
 *  their ₹1,000, so a change request waits for FINANCE), made as the panel makes one (staff.approvals.ask: its inbox
 *  item and audit event follow). */
export function seedFinanceWorld(stamp: number, maker: string): FinanceWorld {
  return lastJson<FinanceWorld>(
    shell(`
import json
from django.utils import timezone
from accounts.models import User
from shop.models import Order, Payment
from staff import approvals
address = {"name": "Real E2E Payer", "phone": "+919864012345", "line1": "1 Test Lane", "line2": "", "city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"}
order = Order.objects.create(email=${py(`admin-ui-payer-${stamp}@example.com`)}, shipping_address=address, subtotal=2400, total=2400, payment_method="razorpay", placed_at=timezone.now(), livemode=True)
Order.objects.filter(pk=order.pk).update(status="paid")
payment = Payment.objects.create(order=order, method="razorpay", amount=2400, razorpay_order_id=${py(`order_e2ef${stamp}`)}, razorpay_payment_id=${py(`pay_e2ef${stamp}`)}, livemode=True)
Payment.objects.filter(pk=payment.pk).update(status="captured")
order.refresh_from_db()
request, _ = approvals.ask("order.refund", maker=User.objects.get(email=${py(maker)}), target=order.number, payload={}, reason="The customer cancelled by phone (the console's tests).")
print(json.dumps({"order": order.number, "payment": payment.pk, "request": request.pk}))
`),
  );
}

/** Deletes what seedFinanceWorld made but its change request (deleteStaff takes it, with its maker) and the audit
 *  events (the log is append-only). */
export function deleteFinanceWorld(world: FinanceWorld) {
  shell(`
from shop.models import Order, Payment
orders = Order.objects.filter(number=${py(world.order)})
Payment.objects.filter(order__in=orders).delete()
print(orders.delete())
`);
}

/** Deletes what seedContent made and what the journey made of it (its reviews and their inbox items) but the audit
 *  events (the log is append-only) and the versions (the history keeps them). */
export function deleteContent(world: ContentWorld) {
  shell(`
from content.models import Book, Paper, ReviewTask
from staff.models import InboxItem
tasks = ReviewTask.objects.filter(paper_id=${world.paper})
InboxItem.objects.filter(target_type="content.reviewtask", target_id__in=[str(pk) for pk in tasks.values_list("pk", flat=True)]).delete()
tasks.delete()
Paper.objects.filter(pk=${world.paper}).delete()
print(Book.objects.filter(pk=${world.book}).delete())
`);
}

/** The authenticator app's code for a moment (RFC 6238: HMAC-SHA1, 30 s, 6 digits). */
export function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.toUpperCase()) bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0xf;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** A code allauth has not seen used yet: each code works once (allauth marks it used for its 30 s), so wait for the
 *  next one when `used` is this one. */
export async function freshCode(secret: string, used: string | null): Promise<string> {
  let code = totp(secret);
  while (code === used) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    code = totp(secret);
  }
  return code;
}
