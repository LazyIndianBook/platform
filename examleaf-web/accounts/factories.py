import factory
from allauth.mfa.models import Authenticator
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
            user._factory_second_factor = True

    @factory.post_generation
    def passkey(user, create, extracted, **kwargs):
        """Staff with an authenticator app have a passkey too, as the privileged roles must (STAFF_PASSKEY_ROLES): its
        row only, never used to sign in. passkey=False: one without (totp=False: neither)."""
        if create and getattr(user, "_factory_second_factor", False) and extracted is not False:
            Authenticator.objects.create(user=user, type=Authenticator.Type.WEBAUTHN, data={"name": "Security key"})
