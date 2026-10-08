"""Each order gets the unguessable token of the link in its emails (SECURITY_REVIEW.md, M2): added empty, filled for the
orders made so far, then made unique."""

import secrets

from django.db import migrations, models

import shop.models


def fill_tokens(apps, schema_editor):
    Order = apps.get_model("shop", "Order")
    for pk in Order.objects.filter(token=None).values_list("pk", flat=True):
        Order.objects.filter(pk=pk).update(token=secrets.token_urlsafe(16))


class Migration(migrations.Migration):
    dependencies = [("shop", "0006_livemode")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="token",
            field=models.CharField(editable=False, max_length=32, null=True),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="token",
            field=models.CharField(default=shop.models.order_token, editable=False, max_length=32, unique=True),
        ),
    ]
