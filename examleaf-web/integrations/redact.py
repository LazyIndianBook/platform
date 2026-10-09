"""What the call log (IntegrationCall.excerpt) and the dead-letter list (IntegrationFailure.args) may keep of a request
or an answer: no secret and no personal data. A password, token or key goes; a phone number keeps its last four
digits, an email address its first letter and its domain, a name goes, an address is reduced to its PIN code, a proof
of delivery (a photograph, a signature) goes; the rest of a JSON body stays, cut to EXCERPT characters. Keys decide
first (Shiprocket's field names), then a pattern catches a phone number or an email address under any other key."""

import json
import re

EXCERPT = 1000
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?[6-9]\d{2}(?:[\s-]?\d){7}(?!\d)")  # 98640 12345, 986-401-2345
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PIN = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")
SECRET_KEYS = ("password", "token", "secret", "api_key", "apikey", "authorization", "otp")  # first: never kept
PHONE_KEYS = ("phone", "mobile", "contact")
EMAIL_KEYS = ("email",)
NAME_KEYS = ("customer_name", "last_name", "first_name", "consignee_name", "consignee", "delivered_to", "name")
ADDRESS_KEYS = ("address", "landmark")
PROOF_KEYS = ("pod", "proof", "qc_image", "signature", "photo")
KEEP_KEYS = ("awb", "_id", "id", "courier_name", "pickup_location", "status", "label", "url", "pincode", "pin_code")


def mask_phone(value):
    digits = re.sub(r"\D", "", str(value))
    return f"******{digits[-4:]}" if len(digits) >= 4 else "******"


def mask_email(value):
    local, _, domain = str(value).partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def mask_address(value):
    pins = PIN.findall(str(value))
    return f"[address, PIN {pins[-1]}]" if pins else "[address]"


def scrub(text):
    """Phone numbers and email addresses in free text."""
    text = PHONE.sub(lambda match: mask_phone(match.group()), text)
    return EMAIL.sub(lambda match: mask_email(match.group()), text)


def _key_kind(key):
    key = str(key).lower()
    if any(name in key for name in SECRET_KEYS):
        return "secret"
    if key.endswith(KEEP_KEYS) or key in KEEP_KEYS:
        return "keep"
    for kind, names in (
        ("proof", PROOF_KEYS),
        ("phone", PHONE_KEYS),
        ("email", EMAIL_KEYS),
        ("address", ADDRESS_KEYS),
    ):
        if any(name in key for name in names):
            return kind
    if key.endswith(NAME_KEYS):
        return "name"
    return ""


def redact(value, key=""):
    """`value` (decoded JSON, or task arguments) with its personal data masked, as the same structure."""
    kind = _key_kind(key) if key else ""
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item, key) for item in value]
    if value is None or isinstance(value, bool) or kind == "keep":
        return value
    if kind == "secret":
        return "[secret]"
    if kind == "proof":
        return "[proof]" if value else value
    if kind == "phone":
        return mask_phone(value) if str(value).strip() else value
    if kind == "email":
        return mask_email(value) if str(value).strip() else value
    if kind == "address":
        return mask_address(value) if str(value).strip() else value
    if kind == "name":
        return "[name]" if str(value).strip() else value
    return scrub(value) if isinstance(value, str) else value


def excerpt(body, limit=EXCERPT):
    """A redacted excerpt of a request's or an answer's body (bytes, text or decoded JSON), at most `limit` characters;
    a body that is not text (a PDF) is described, not copied."""
    if body is None or body in (b"", ""):
        return ""
    if isinstance(body, bytes):
        if body.startswith(b"%PDF"):
            return f"[PDF, {len(body)} bytes]"
        body = body.decode("utf-8", "replace")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return scrub(body)[: min(limit, 300)]
    return json.dumps(redact(body), ensure_ascii=False, separators=(",", ":"), default=str)[:limit]
