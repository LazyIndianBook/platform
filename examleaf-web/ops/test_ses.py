"""Amazon SES (ops/ses.py): the tracking webhook verifies each SNS message's signature and topic before anymail reads
it (a known-good message passes, a tampered one, another topic's or one signed elsewhere does not), the signing
certificate is fetched from SNS's own host only and kept; SES's suppression list joins ours, idempotently."""

import base64
import json
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from anymail.exceptions import AnymailWebhookValidationFailure
from botocore.stub import Stubber
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.core.cache import cache
from django.test import RequestFactory

from ops import ses
from ops.models import EmailStat, EmailSuppression

pytestmark = pytest.mark.django_db
TOPIC = "arn:aws:sns:ap-south-1:123456789012:examleaf-ses"
CERT_URL = "https://sns.ap-south-1.amazonaws.com/SimpleNotificationService-0000000000000000000000.pem"


@pytest.fixture(scope="module")
def signer():
    """A key and its self-signed certificate, standing in for SNS's (whose certificate is never fetched here)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return key, certificate.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def sns(settings, signer, monkeypatch):
    """SNS_TOPIC restricted, the certificate served from the cache's stand-in; returns a signer of messages."""
    settings.SES_SNS_TOPIC_ARN = TOPIC
    key, pem = signer
    fetched = []
    monkeypatch.setattr(ses, "fetch_certificate", lambda url: fetched.append(url) or pem)

    def sign(message, version="2"):
        message = {"SignatureVersion": version, "SigningCertURL": CERT_URL, "TopicArn": TOPIC, **message}
        digest = hashes.SHA256() if version == "2" else hashes.SHA1()
        signature = key.sign(ses.canonical(message).encode(), padding.PKCS1v15(), digest)
        return {**message, "Signature": base64.b64encode(signature).decode()}

    sign.fetched = fetched
    return sign


def bounce(recipient="gone@example.com"):
    event = {
        "eventType": "Bounce",
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [{"emailAddress": recipient}],
            "timestamp": "2026-10-09T10:00:00.000Z",
        },
        "mail": {"messageId": "ses-message-1", "timestamp": "2026-10-09T09:59:00.000Z", "destination": [recipient]},
    }
    return {
        "Type": "Notification",
        "MessageId": "sns-message-1",
        "Message": json.dumps(event),
        "Timestamp": "2026-10-09T10:00:01.000Z",
    }


def post(message):
    request = RequestFactory().post(
        "/anymail/amazon_ses/tracking/",
        data=json.dumps(message),
        content_type="text/plain",
        HTTP_X_AMZ_SNS_MESSAGE_TYPE=message.get("Type", ""),
        HTTP_X_AMZ_SNS_MESSAGE_ID=message.get("MessageId", ""),
    )
    return ses.SesTrackingView.as_view()(request)


def test_a_signed_message_from_our_topic_passes_in_both_signature_versions(sns):
    assert ses.sns_problem(sns(bounce())) == ""
    assert ses.sns_problem(sns(bounce(), version="1")) == ""


def test_a_tampered_message_another_topic_or_another_signer_is_refused(sns, settings):
    signed = sns(bounce())
    assert (
        ses.sns_problem({**signed, "Message": signed["Message"].replace("gone@", "other@")}) == "its signature is wrong"
    )
    assert ses.sns_problem({**signed, "Timestamp": "2026-10-09T11:00:00.000Z"}) == "its signature is wrong"
    assert ses.sns_problem({**signed, "Signature": "not base64!"}) == "its signature is wrong"
    other = sns({**bounce(), "TopicArn": "arn:aws:sns:ap-south-1:999999999999:theirs"})
    assert ses.sns_problem(other) == "it is not from SES_SNS_TOPIC_ARN"
    for url in [
        "http://sns.ap-south-1.amazonaws.com/x.pem",
        "https://sns.evil.example/x.pem",
        "https://sns.ap-south-1.amazonaws.com.evil.example/x.pem",
        "https://s3.amazonaws.com/x.pem",
        "https://sns.ap-south-1.amazonaws.com:8443/x.pem",
    ]:
        assert ses.sns_problem({**signed, "SigningCertURL": url}) == "its signing certificate is not SNS's", url
    assert ses.sns_problem({**signed, "SignatureVersion": "3"}) == "an unknown signature version"
    assert ses.sns_problem({"Type": "Something"}) == "not an SNS message"
    settings.SES_SNS_TOPIC_ARN = ""  # unrestricted (basic auth is then the control): any topic's signature counts
    assert ses.sns_problem(other) == ""


def test_the_tracking_webhook_suppresses_a_verified_bounce_and_counts_it(sns):
    assert post(sns(bounce())).status_code == 200
    assert EmailSuppression.objects.get().email == "gone@example.com"
    assert EmailStat.objects.get(event="bounced").count == 1
    tampered = sns(bounce())
    tampered["Message"] = tampered["Message"].replace("gone@", "victim@")
    with pytest.raises(AnymailWebhookValidationFailure):  # a 400 through Django's handler
        post(tampered)
    assert not EmailSuppression.objects.filter(email="victim@example.com").exists()


def test_the_certificate_is_fetched_from_sns_once_and_kept(monkeypatch, signer):
    import httpx

    _, pem = signer
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs.get("follow_redirects")))
        return httpx.Response(200, text=pem, request=httpx.Request("GET", url))

    monkeypatch.setattr(ses.httpx, "get", get)
    cache.clear()
    assert ses.fetch_certificate(CERT_URL) == pem and ses.fetch_certificate(CERT_URL) == pem
    assert calls == [(CERT_URL, False)]  # once, and never following a redirect elsewhere


def test_ses_suppressions_join_ours_and_a_second_run_adds_nothing():
    EmailSuppression.objects.create(email="known@example.com", reason="bounce", esp="Amazon SES")
    client = boto3.client("sesv2", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="y")
    pages = [
        {
            "SuppressedDestinationSummaries": [
                {"EmailAddress": "Known@Example.com", "Reason": "BOUNCE", "LastUpdateTime": datetime(2026, 10, 1)},
                {"EmailAddress": "spam@example.com", "Reason": "COMPLAINT", "LastUpdateTime": datetime(2026, 10, 2)},
            ],
            "NextToken": "page-2",
        },
        {"SuppressedDestinationSummaries": [
            {"EmailAddress": "gone@example.com", "Reason": "BOUNCE", "LastUpdateTime": datetime(2026, 10, 3)}]},
    ]  # fmt: skip
    with Stubber(client) as stub:
        for _ in range(2):  # two runs
            stub.add_response("list_suppressed_destinations", pages[0], {"PageSize": 1000})
            stub.add_response("list_suppressed_destinations", pages[1], {"PageSize": 1000, "NextToken": "page-2"})
        assert ses.sync_suppressions(client) == {"read": 3, "added": 2}
        assert ses.sync_suppressions(client) == {"read": 3, "added": 0}
    assert dict(EmailSuppression.objects.values_list("email", "reason")) == {
        "known@example.com": "bounce",
        "spam@example.com": "complaint",
        "gone@example.com": "bounce",
    }
    assert cache.get(ses.SUPPRESSIONS_SYNCED) is not None
