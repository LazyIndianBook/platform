import csv
import re
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from localflavor.in_.in_states import STATE_CHOICES

from shop.models import PinCode

# The directory's state names, in capitals, besides the names of localflavor's list (older files spell some the old
# way). A name in none of them stops the import: add it here.
ALIASES = {
    "CHATTISGARH": "CT",
    "ORISSA": "OR",
    "PONDICHERRY": "PY",
    "UTTARANCHAL": "UT",
    "DADRA AND NAGAR HAVELI": "DH",
    "DAMAN AND DIU": "DH",
}
CODES = {name.upper(): code for code, name in STATE_CHOICES} | ALIASES


def state_code(name):
    """'JAMMU & KASHMIR', 'The Dadra And Nagar Haveli And Daman And Diu' -> 'JK', 'DH'; None if unknown."""
    name = re.sub(r"\s+", " ", name.upper().replace("&", " AND ")).strip().removeprefix("THE ")
    return CODES.get(name)


class Command(BaseCommand):
    help = (
        "Replace the PIN code table with the India Post directory: the CSV of data.gov.in's \"All India Pincode "
        'Directory" (DEPLOYMENT.md), one row per post office. Run it again with each yearly download.'
    )

    def add_arguments(self, parser):
        parser.add_argument("csv", help="the downloaded CSV file")

    def handle(self, **options):
        found = defaultdict(lambda: (set(), set()))  # pin: (state codes, districts)
        unknown = set()
        with open(options["csv"], newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                row = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
                if not re.fullmatch(r"[1-9]\d{5}", row.get("pincode", "")):
                    continue
                if (code := state_code(row["statename"])) is None:
                    unknown.add(row["statename"])
                    continue
                states, districts = found[row["pincode"]]
                states.add(code)
                districts.add(row["district"].title())
        if unknown:
            raise CommandError(f"Unknown state names (add them to ALIASES): {', '.join(sorted(unknown))}")
        if not found:
            raise CommandError("No PIN codes in this file: is it the directory's CSV?")
        with transaction.atomic():
            PinCode.objects.all().delete()
            PinCode.objects.bulk_create(
                (PinCode(pin=pin, states=sorted(s), districts=sorted(d)) for pin, (s, d) in found.items()),
                batch_size=2000,
            )
        self.stdout.write(f"{len(found)} PIN codes loaded.")
