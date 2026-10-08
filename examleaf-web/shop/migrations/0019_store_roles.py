"""The role groups get the permissions of the store's new models (accounts/roles.py: CONTENT_EDITOR the catalogue,
SALES offers, staff orders, offline payments, notes, reviews and quotations), as 0002_roles did. Deploys also run
bootstrap_roles after migrate, which does the same for every app (the learn app's permissions included)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from accounts.roles import sync_roles


def store_roles(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps.get_model("auth", "Group"), apps.get_model("auth", "Permission"))


class Migration(migrations.Migration):
    dependencies = [("shop", "0018_staff_orders")]
    operations = [migrations.RunPython(store_roles, migrations.RunPython.noop)]
