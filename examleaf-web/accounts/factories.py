import factory

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
