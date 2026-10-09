from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_roles_after_migrate(sender, using="default", apps=None, **kwargs):
    """After every `migrate` (and a test database's flush) the role groups hold exactly accounts.roles.ROLES. Django
    creates permissions app by app, so every app's are created first; a fresh database then needs no role migration
    and no bootstrap_roles (which does the same by hand)."""
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    from accounts.roles import sync_roles

    registry = apps or global_apps
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using, apps=registry)
    sync_roles(registry.get_model("auth", "Group"), registry.get_model("auth", "Permission"))


class StaffConfig(AppConfig):
    name = "staff"
    verbose_name = "Staff (the Admin Control Panel)"

    def ready(self):
        post_migrate.connect(sync_roles_after_migrate, sender=self, dispatch_uid="staff.sync_roles")
