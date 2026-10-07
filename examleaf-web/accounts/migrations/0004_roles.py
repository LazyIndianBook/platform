"""The role groups (accounts/roles.py). Permissions are normally created after all migrations (post_migrate), so they
are created here first for the apps migrated so far."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from accounts.roles import sync_roles


def create_roles(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps.get_model("auth", "Group"), apps.get_model("auth", "Permission"))


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_teacher_consent_deletion"),
        ("account", "0009_emailaddress_unique_primary_email"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("content", "0001_initial"),
        ("pages", "0002_legal_pages"),
        ("practice", "0001_initial"),
    ]
    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
