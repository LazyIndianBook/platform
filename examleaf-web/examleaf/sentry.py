"""What an error report may carry to Sentry. send_default_pii=False (settings.py) keeps out cookies, the user and the
client address, and include_local_variables=False the variables of the stack frames; `before_send` then goes through
the whole event (request body, query and headers, breadcrumbs, extra) and replaces the values of secret or personal
fields, and card numbers, Indian mobile numbers and email addresses inside any text, with "[Filtered]". An email's
text ("body", "alternatives") and log messages ("message") are filtered whole: they can hold reset links and codes."""

import re

FILTERED = "[Filtered]"
KEYS = {  # field names, lower case, "-" read as "_" (headers)
    *["password", "password1", "password2", "new_password1", "new_password2", "old_password"],
    *["code", "verification_token", "refresh", "access", "token", "key", "authorization", "cookie"],
    *["otp", "var1", "var2", "authkey"],  # an SMS task's variables (ops/sms.py): code, a name, a consent link's token
    *["razorpay_signature", "x_razorpay_signature", "secret", "body", "alternatives", "message"],
    *["email", "full_name", "parent_name", "date_of_birth", "shipping_address", "line1", "line2", "pin", "vpa"],
}
KEY_PARTS = ("card", "cvv", "phone", "mobile", "contact", "password", "secret")  # card_number, parent_contact, …
NUMBERS = re.compile(
    r"(?<!\d)(?:\+?91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)"  # an Indian mobile number
    r"|(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"  # a card number (13 to 19 digits)
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"  # an email address
)
STRUCTURE = {"event_id", "contexts", "sdk", "modules", "debug_meta"}  # ids and versions, never personal


def scrub(value, key=""):
    name = key.lower().replace("-", "_") if isinstance(key, str) else ""
    if name in KEYS or any(part in name for part in KEY_PARTS):
        return FILTERED
    if isinstance(value, dict):
        return {k: v if k in STRUCTURE else scrub(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return NUMBERS.sub(FILTERED, value)
    return value


def before_send(event, hint):
    return scrub(event)
