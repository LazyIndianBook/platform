from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from accounts.roles import ROLES, sync_roles


class Command(BaseCommand):
    help = "Create the role groups (accounts/roles.py) and set their permissions. Safe to run again; run after migrate."

    def handle(self, *args, **options):
        missing = sync_roles(Group, Permission)
        for name in ROLES:
            self.stdout.write(f"{name}: {Group.objects.get(name=name).permissions.count()} permissions")
        if missing:
            self.stderr.write(f"Not found (app not migrated yet?): {', '.join(missing)}")
