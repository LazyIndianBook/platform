"""The app's log-in by SMS code (api/auth.py): allauth's login-by-code process in a throw-away session, the same JWT
pair as a password log-in, generic errors, three attempts per token. Its imports come from allauth.account.internal:
an allauth upgrade that moves them fails here."""

import re

import pytest
from rest_framework.test import APIClient

from api.tests import student

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning"),  # the short development SECRET_KEY
]
CODE, CONFIRM = "/api/v1/auth/phone/code/", "/api/v1/auth/phone/confirm/"


@pytest.fixture
def api():
    return APIClient()


def texted_codes(capsys):
    return re.findall(r"'otp': '(\d{6})'", capsys.readouterr().out)


def test_a_texted_code_logs_the_app_in_once(api, capsys):
    user = student(login_phone="+919864012345", login_phone_verified=True)
    response = api.post(CODE, {"phone": "98640 12345"}, format="json")
    assert response.status_code == 200 and "sessionid" not in response.cookies
    token, [code] = response.json()["verification_token"], texted_codes(capsys)
    response = api.post(CONFIRM, {"verification_token": token, "code": code}, format="json")
    assert response.status_code == 200 and response.json()["user"]["email"] == user.email
    assert {"access", "refresh"} <= response.json().keys()
    assert api.post(CONFIRM, {"verification_token": token, "code": code}, format="json").status_code == 400  # spent


def test_unknown_numbers_get_a_token_no_sms_and_the_same_error(api, capsys):
    response = api.post(CODE, {"phone": "98640 12345"}, format="json")
    assert response.status_code == 200 and texted_codes(capsys) == []
    token = response.json()["verification_token"]
    response = api.post(CONFIRM, {"verification_token": token, "code": "123456"}, format="json")
    assert response.status_code == 400 and "code" in response.json()
    assert api.post(CODE, {"phone": "12345"}, format="json").json() == {
        "phone": ["Enter a 10-digit Indian mobile number."]
    }


def test_three_wrong_codes_end_the_token_and_three_requests_an_hour_per_number(api, capsys):
    student(login_phone="+919864012345", login_phone_verified=True)
    token = api.post(CODE, {"phone": "98640 12345"}, format="json").json()["verification_token"]
    [code] = texted_codes(capsys)
    for _ in range(3):
        api.post(CONFIRM, {"verification_token": token, "code": "000000"}, format="json")
    response = api.post(CONFIRM, {"verification_token": token, "code": code}, format="json")
    assert response.json() == {"verification_token": ["Expired. Ask for a new code."]}
    api.post(CODE, {"phone": "+91 98640 12345"}, format="json")
    api.post(CODE, {"phone": "098640 12345"}, format="json")
    assert api.post(CODE, {"phone": "9864012345"}, format="json").status_code == 429  # one number however typed
