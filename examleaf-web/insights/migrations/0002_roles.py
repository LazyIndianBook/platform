"""Give the role groups the permissions of every app migrated so far (accounts/roles.py: ADMIN those of insights), as
shop.0019_store_roles did for the store. Needed here too because insights' first migration needs the shop's last, so
a fresh database now migrates the shop (and its role sync) before the learn app. Deploys also run bootstrap_roles
after migrate, which does the same for every app."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from accounts.roles import sync_roles


def insights_roles(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps.get_model("auth", "Group"), apps.get_model("auth", "Permission"))


class Migration(migrations.Migration):
    dependencies = [("insights", "0001_initial"), ("accounts", "0004_roles")]
    operations = [migrations.RunPython(insights_roles, migrations.RunPython.noop)]
