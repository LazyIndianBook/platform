"""Keep only the allowed fields (Payment.PAYLOAD_FIELDS) of the webhooks stored so far: they held the whole event,
with the payer's email, phone, UPI ID and card details (SECURITY_REVIEW.md, M6)."""

from django.db import migrations

FIELDS = "id order_id status method amount currency error_code error_description created_at".split()


def strip_payloads(apps, schema_editor):
    Payment = apps.get_model("shop", "Payment")
    for payment in Payment.objects.filter(raw_payload__isnull=False).only("raw_payload"):
        event = payment.raw_payload if isinstance(payment.raw_payload, dict) else {}
        entity = event.get("payload", {}).get("payment", {}).get("entity", event)  # stripped already: as it is
        kept = {name: entity[name] for name in FIELDS if name in entity}
        Payment.objects.filter(pk=payment.pk).update(raw_payload=kept or None)


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_credit_notes_webhook_events")]
    operations = [migrations.RunPython(strip_payloads, migrations.RunPython.noop)]
