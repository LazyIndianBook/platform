from django.core.management.base import BaseCommand

from shop import payments


class Command(BaseCommand):
    help = (
        "Ask Razorpay about every online order still awaiting payment (older than --older-than minutes), staff orders' "
        "links included, and record the payments it made that the site never heard about (RUNBOOK.md, a stuck "
        "payment). The same runs each night at 02:30 (shop.tasks.reconcile_payments)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--older-than", type=int, default=10, help="minutes (a customer may be paying right now)")

    def handle(self, older_than, **options):
        results = {True: "paid now", False: "no payment at Razorpay", None: "Razorpay could not be asked"}
        for order in payments.awaiting_payment(older_than):
            self.stdout.write(f"{order.number}: {results[payments.reconcile(order)]}")
        self.stdout.write("Done.")
