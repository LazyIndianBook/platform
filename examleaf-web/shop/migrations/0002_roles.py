"""Give the role groups their shop permissions (accounts/roles.py), as accounts.0004_roles did for the apps before the
shop. Deploys also run bootstrap_roles after migrate, which does the same for every app."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from accounts.roles import sync_roles


def shop_roles(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps.get_model("auth", "Group"), apps.get_model("auth", "Permission"))


class Migration(migrations.Migration):
    dependencies = [("shop", "0001_initial"), ("accounts", "0004_roles")]
    operations = [migrations.RunPython(shop_roles, migrations.RunPython.noop)]
