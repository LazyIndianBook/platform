"""Delete the review's temporary student and everything it made (dry run unless APPLY=1).

From examleaf-web, with DATABASE_URL pointing at the database the review used:
    .venv/bin/python manage.py shell < cleanup-temp-user.py              # list what would go
    APPLY=1 .venv/bin/python manage.py shell < cleanup-temp-user.py      # delete it

The user's cart, address, consent records, marks attempt, learner row and sessions go with the account. The unpaid
order (the account's deletion only anonymises orders) is cancelled so that its stock goes back, then deleted with its
payment rows and the history rows of those. Nothing of a paid order is touched: the script refuses.
"""
import os

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction

from shop import services
from shop.models import Order, OrderNote, Payment

EMAIL = "nx-review-temp@example.com"
APPLY = os.environ.get("APPLY") == "1"

user = get_user_model().objects.filter(email__iexact=EMAIL).first()
assert user is None or not (user.is_staff or user.is_superuser), "refusing to delete a staff account"
orders = list(Order.objects.filter(email__iexact=EMAIL))
assert all(o.placed_at is None and o.status in (Order.Status.PENDING, Order.Status.CANCELLED) for o in orders), "a paid order exists"
sessions = [s.pk for s in Session.objects.all() if user and s.get_decoded().get("_auth_user_id") == str(user.pk)]
print("user:", user and (user.pk, user.email), "| orders:", [o.number for o in orders], "| sessions:", len(sessions), "| apply:", APPLY)

if APPLY:
    with transaction.atomic():
        for order in orders:
            if order.status == Order.Status.PENDING:
                services.cancel_order(order, "review clean-up", email=False)  # puts the reserved stock back
            payments = list(order.payments.values_list("pk", flat=True))
            notes = list(order.notes.values_list("pk", flat=True))
            order.payments.all().delete()
            pk = order.pk
            order.delete()
            Order.history.filter(id=pk).delete()
            Payment.history.filter(id__in=payments).delete()
            OrderNote.history.filter(id__in=notes).delete()
        Session.objects.filter(pk__in=sessions).delete()
        if user:
            user.delete()
    print("left: user", get_user_model().objects.filter(email__iexact=EMAIL).count(),
          "| orders", Order.objects.filter(email__iexact=EMAIL).count(),
          "| order history", Order.history.filter(email__iexact=EMAIL).count())
