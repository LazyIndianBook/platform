from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop import payments
from shop.models import Order


class Command(BaseCommand):
    help = (
        "Ask Razorpay about every online order still awaiting payment (older than --older-than minutes) and record the "
        "payments it made that the site never heard about (RUNBOOK.md, a stuck payment)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--older-than", type=int, default=10, help="minutes (a customer may be paying right now)")

    def handle(self, older_than, **options):
        pending = Order.objects.filter(
            status=Order.Status.PENDING,
            placed_at__isnull=True,
            payment_method=Order.Method.RAZORPAY,
            created__lt=timezone.now() - timedelta(minutes=older_than),
        ).exclude(payments__razorpay_order_id=None)
        results = {True: "paid now", False: "no payment at Razorpay", None: "Razorpay could not be asked"}
        for order in pending.distinct():
            self.stdout.write(f"{order.number}: {results[payments.reconcile(order)]}")
        self.stdout.write("Done.")
