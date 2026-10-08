import datetime
from django.contrib.auth.models import Group
from django.utils import timezone
from accounts.models import User
from content.models import Board

EMAIL = "nx-review-temp@example.com"
user, created = User.objects.get_or_create(
    email=EMAIL,
    defaults=dict(full_name="Review Temp", class_level=12, board=Board.objects.first(),
                  date_of_birth=datetime.date(2000, 1, 1), consent_at=timezone.now(), is_staff=False, is_superuser=False),
)
if created:
    user.set_unusable_password(); user.save()
user.groups.add(Group.objects.get(name="STUDENT"))
assert not user.is_staff and not user.is_superuser
# allauth needs a verified primary email address for code login
from allauth.account.models import EmailAddress
EmailAddress.objects.update_or_create(user=user, email=EMAIL, defaults=dict(verified=True, primary=True))
print("USER", user.pk, user.email, "created" if created else "existed", "staff", user.is_staff)
