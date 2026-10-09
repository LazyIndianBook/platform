"""Amazon SES's side of email (research-integrations 4.4): the tracking webhook's SNS signature verified, and SES's
account-level suppression list kept in step with ours (ops.models.EmailSuppression).

The webhook (/anymail/amazon_ses/tracking/, examleaf/urls.py) is anymail's, which reads SES's bounces and complaints
but verifies no SNS signature. SesTrackingView verifies each message first (sns_problem): the signing certificate's
address must be https://sns.<region>.amazonaws.com/….pem (fetched once and kept a day), the signature over the SNS
canonical string must be its key's (SignatureVersion 1, SHA1; 2, SHA256), and the topic must be SES_SNS_TOPIC_ARN when
that is set. AWS signs every topic's messages, so a signature alone does not say the topic is ours: the address exists
only with the topic restricted (SES_SNS_TOPIC_ARN) or with ANYMAIL_WEBHOOK_SECRET's basic auth, anymail's own control,
and with both in production (DEPLOYMENT.md section 25)."""

import base64
import hashlib
import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from anymail.exceptions import AnymailAPIError, AnymailWebhookValidationFailure
from anymail.webhooks.amazon_ses import AmazonSESTrackingWebhookView
from anymail.webhooks.base import AnymailBasicAuthMixin
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)
CERT_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?$")
CERT_KEPT = 24 * 3600  # seconds: a certificate is fetched once a day at most
CERT_TIMEOUT = httpx.Timeout(3)
SIGNED = {  # the fields each message type signs, in the canonical order (AWS SNS developer guide)
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
    "UnsubscribeConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
}
SUPPRESSIONS_SYNCED = "ops:ses-suppressions-synced"  # when SES's list was last read (the connections card)


def canonical(message):
    """The string SNS signs: each signed field present, as "Name\\nValue\\n" in the canonical order."""
    names = SIGNED.get(message.get("Type"), [])
    return "".join(f"{name}\n{message[name]}\n" for name in names if message.get(name) is not None)


def certificate_url_problem(url):
    parts = urlsplit(url or "")
    if parts.scheme != "https" or not CERT_HOST.match(parts.hostname or "") or not parts.path.endswith(".pem"):
        return "its signing certificate is not SNS's"
    if parts.port not in (None, 443) or parts.username or parts.password:
        return "its signing certificate is not SNS's"
    return ""


def fetch_certificate(url):
    """The PEM text of SNS's signing certificate at `url` (checked first), kept a day in the cache."""
    key = f"ops:sns-cert:{hashlib.sha256(url.encode()).hexdigest()}"
    if pem := cache.get(key):
        return pem
    response = httpx.get(url, timeout=CERT_TIMEOUT, follow_redirects=False)
    response.raise_for_status()
    pem = response.text
    if "BEGIN CERTIFICATE" not in pem:
        raise ValueError("not a certificate")
    cache.set(key, pem, CERT_KEPT)
    return pem


def sns_problem(message, now=None):
    """Why an SNS message must be refused, or "" when its signature is SNS's and its topic ours."""
    if not isinstance(message, dict) or message.get("Type") not in SIGNED:
        return "not an SNS message"
    topic = settings.SES_SNS_TOPIC_ARN
    if topic and message.get("TopicArn") != topic:
        return "it is not from SES_SNS_TOPIC_ARN"
    if problem := certificate_url_problem(message.get("SigningCertURL")):
        return problem
    version = str(message.get("SignatureVersion", ""))
    if version not in ("1", "2"):
        return "an unknown signature version"
    try:
        signature = base64.b64decode(message.get("Signature") or "", validate=True)
    except ValueError:
        return "its signature is wrong"
    try:
        pem = fetch_certificate(message["SigningCertURL"])
        certificate = x509.load_pem_x509_certificate(pem.encode())
    except (httpx.HTTPError, ValueError, TypeError) as error:
        logger.warning("SNS signing certificate unusable: %s", type(error).__name__)
        return "its signing certificate could not be read"
    now = now or timezone.now()
    if not (certificate.not_valid_before_utc <= now.astimezone(UTC) <= certificate.not_valid_after_utc):
        return "its signing certificate is not valid now"
    digest = hashes.SHA1() if version == "1" else hashes.SHA256()  # noqa: S303  SNS's version 1 is SHA1, by AWS
    try:
        certificate.public_key().verify(signature, canonical(message).encode(), padding.PKCS1v15(), digest)
    except InvalidSignature, TypeError, ValueError:
        return "its signature is wrong"
    return ""


class SesTrackingView(AmazonSESTrackingWebhookView):
    """anymail's SES tracking webhook, each message's SNS signature and topic verified first (400 otherwise: a
    validation failure, which SNS does not retry for long and nobody else should send)."""

    @property
    def warn_if_no_basic_auth(self):  # the topic restriction is the control then (examleaf/urls.py)
        return not settings.SES_SNS_TOPIC_ARN

    def validate_request(self, request):
        AnymailBasicAuthMixin.validate_request(self, request)  # the cheap check first (anymail runs it again after)
        try:
            message = self._parse_sns_message(request)
        except AnymailAPIError:
            raise AnymailWebhookValidationFailure("SNS message refused: not JSON") from None
        if problem := sns_problem(message):
            logger.warning("SES tracking webhook refused: %s", problem)
            raise AnymailWebhookValidationFailure(f"SNS message refused: {problem}")


def mounted():
    """Whether the tracking webhook exists: with SES as the backend (or anymail's secret set) and a control that says
    the topic is ours (ANYMAIL_WEBHOOK_SECRET, SES_SNS_TOPIC_ARN)."""
    return bool(settings.ANYMAIL.get("WEBHOOK_SECRET") or settings.SES_SNS_TOPIC_ARN)


def suppressed_addresses(client):
    """Every address on SES's account-level suppression list, with its reason (BOUNCE or COMPLAINT), page by page."""
    token = None
    while True:
        page = client.list_suppressed_destinations(**({"NextToken": token} if token else {}), PageSize=1000)
        for row in page.get("SuppressedDestinationSummaries") or []:
            if row.get("EmailAddress"):
                yield row["EmailAddress"].strip().lower(), row.get("Reason", "")
        token = page.get("NextToken")
        if not token:
            return


def sync_suppressions(client=None):
    """SES's suppression list into ours: the addresses missing here added (a complaint as a complaint, a bounce as a
    bounce), none removed (an address we suppressed stays so). Run twice, it adds nothing the second time. Returns
    {"read", "added"}."""
    from integrations.connections import logged_call, ses_client
    from integrations.models import IntegrationAccount

    from .models import EmailSuppression

    client = client or ses_client()
    account, _ = IntegrationAccount.objects.get_or_create(
        provider="ses", mode="live", defaults={"label": "The environment's keys"}
    )
    found = logged_call(
        account,
        "list_suppressed_destinations",
        "sesv2/suppression/addresses",
        lambda: dict(suppressed_addresses(client)),
    )
    have = set(EmailSuppression.objects.filter(email__in=list(found)).values_list("email", flat=True))
    missing = [
        EmailSuppression(
            email=email,
            reason=EmailSuppression.Reason.COMPLAINT if reason == "COMPLAINT" else EmailSuppression.Reason.BOUNCE,
            esp="Amazon SES",
        )
        for email, reason in found.items()
        if email not in have and len(email) <= 254
    ]
    EmailSuppression.objects.bulk_create(missing, ignore_conflicts=True)
    cache.set(SUPPRESSIONS_SYNCED, datetime.now(UTC), 8 * 24 * 3600)
    return {"read": len(found), "added": len(missing)}
