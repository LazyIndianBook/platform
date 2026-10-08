import factory
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

from .models import User

PASSWORD = "Brahmaputra-2027"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"student{n}@example.com")
    full_name = factory.Faker("name", locale="en_IN")
    password = factory.django.Password(PASSWORD)
    class_level = 12

    @factory.post_generation
    def totp(user, create, extracted, **kwargs):
        """Staff have an authenticator app, as the site requires (StaffMFAMiddleware); totp=False: one without."""
        if create and user.is_staff and extracted is not False:
            TOTP.activate(user, generate_totp_secret())
