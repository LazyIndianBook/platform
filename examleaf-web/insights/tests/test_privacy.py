"""Aggregate only (DPDP Act s. 9(3)): nothing in insights points to an account or a learner, or holds who they are."""

from django.apps import apps
from django.conf import settings


def test_no_insights_model_has_a_key_to_an_account_or_a_learner():
    people = {apps.get_model(settings.AUTH_USER_MODEL), apps.get_model("learn", "Learner")}
    for model in apps.get_app_config("insights").get_models():
        for field in model._meta.get_fields():
            assert not (field.is_relation and field.related_model in people), f"{model.__name__}.{field.name}"


def test_no_insights_field_holds_a_name_or_a_contact():
    names = {field.name for model in apps.get_app_config("insights").get_models() for field in model._meta.fields}
    personal = {"user", "learner", "email", "phone", "ip", "ip_address", "name", "full_name", "address", "pin"}
    assert not names & personal  # accounts, addresses and codes are kept as keyed hashes (…_hash, subject)
