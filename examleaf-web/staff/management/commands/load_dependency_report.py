import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from staff.system_api import save_dependency_report


class Command(BaseCommand):
    help = (
        "Keep CI's dependency report (dependency-report.json: pip-audit's and npm audit's advisories, made by "
        "scripts/dependency_report.py) in the private storage at DEPENDENCY_REPORT_PATH, for the System page; "
        "each advisory keeps the day it was first seen. Run by the deploy (DEPLOYMENT.md section 25)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="the report CI made (an artifact of the deploy's commit)")

    def handle(self, path, **options):
        try:
            report = json.loads(Path(path).read_text())
            rows = save_dependency_report(report)
        except (OSError, ValueError) as error:
            raise CommandError(f"Not loaded: {error}") from error
        self.stdout.write(f"Loaded: {len(rows)} open advisories.")
