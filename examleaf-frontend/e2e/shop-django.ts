// The shop tests' fixtures in the Django backend (manage.py shell): a student with a confirmed email address and a
// saved address, a delivered order (for the review form), and the clean-up of everything they made: their orders
// (pending ones cancelled first, so their stock is released), reviews and the account itself.
import { execFileSync } from "node:child_process";
import path from "node:path";

import { djangoEnv } from "../playwright.config";

const DJANGO_DIR = path.resolve(__dirname, "../../examleaf-web");

function shell(code: string): string {
  const python = process.env.DJANGO_PYTHON ?? path.join(DJANGO_DIR, ".venv/bin/python");
  return execFileSync(python, ["manage.py", "shell", "-c", code], {
    cwd: DJANGO_DIR,
    env: { ...process.env, ...djangoEnv },
    stdio: "pipe",
  }).toString();
}

const py = (value: string) => JSON.stringify(value);

export function createShopper(email: string, password: string) {
  shell(`
from datetime import date
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import User
from shop.models import Address
user = User.objects.create_user(${py(email)}, ${py(password)}, full_name="E2E Shopper", class_level=12, date_of_birth=date(2000, 1, 1), consent_at=timezone.now())
EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
Address.objects.create(user=user, name="E2E Shopper", phone="+919864012345", line1="1 Test Lane", city="Guwahati", district="Kamrup Metro", state="AS", pin="781001", is_default=True)
`);
}

/** A delivered order of `product` for the account: its buyer may review it. */
export function deliverOrder(email: string, product: string) {
  shell(`
from django.utils import timezone
from accounts.models import User
from shop.models import Order, OrderItem, Product
user = User.objects.get(email=${py(email)})
book = Product.objects.get(slug=${py(product)})
address = {"name": "E2E Shopper", "phone": "+919864012345", "line1": "1 Test Lane", "line2": "", "city": "Guwahati", "district": "Kamrup Metro", "state": "AS", "pin": "781001"}
order = Order.objects.create(user=user, email=user.email, shipping_address=address, subtotal=book.price.amount, total=book.price.amount, payment_method="cod", placed_at=timezone.now())
OrderItem.objects.create(order=order, product=book, title=book.title, hsn_code=book.hsn_code, gst_rate=book.gst_rate, mrp=book.mrp.amount, unit_price=book.price.amount, quantity=1)
Order.objects.filter(pk=order.pk).update(status="delivered")
`);
}

export function deleteShopper(email: string) {
  shell(`
from accounts.models import User
from shop import services
from shop.models import CreditNote, Invoice, Order, Payment, Refund, Review, StockAlert
orders = Order.objects.filter(email=${py(email)})
for order in orders.filter(status="pending"):
    try:
        services.cancel_order(order, "E2E clean-up", email=False)
    except Exception as error:
        print("not cancelled", order, error)
CreditNote.objects.filter(invoice__order__in=orders).delete()
Refund.objects.filter(order__in=orders).delete()
Invoice.objects.filter(order__in=orders).delete()
Payment.objects.filter(order__in=orders).delete()
orders.delete()
Review.objects.filter(user__email=${py(email)}).delete()
StockAlert.objects.filter(email=${py(email)}).delete()
User.objects.filter(email=${py(email)}).delete()
`);
}

/** The secret of an order's emailed link (/orders/t/<token>/): only the order's emails carry it. */
export function orderToken(number: string): string {
  return shell(`
from shop.models import Order
print(Order.objects.get(number=${py(number)}).token)
`)
    .trim()
    .split("\n")
    .pop()!; // after the shell's own "objects imported" line
}
