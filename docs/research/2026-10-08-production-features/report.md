# ExamLeaf production features: research report

Date: 2026-10-08. Read from the repository: Django 6.1.2, Python 3.14.2, django-allauth 65.19.7 (+ allauth.mfa, fido2 2.2.1), django-storages 1.14.6, django-anymail 15.2, Celery 5.6.3, DRF 3.18.3 + dj-rest-auth 7.2.0 + simplejwt, Pillow 12.3.0, strict CSP (`script-src 'self'` + KaTeX, `form-action 'self'`), Caddy, a cache that fails open when Redis is down, `User.phone` as a free-text profile field, `Shipment.tracking_url`, `ship_order(order, courier, tracking_number, tracking_url="")`.

Evidence labels: **[ran]** executed by me on Python 3.14.2 / Django 6.1.2 in a throw-away venv or read from the installed source; **[doc]** official documentation or changelog fetched today; **[2nd]** vendor blog, aggregator or search summary (a pointer only: confirm in the vendor dashboard). Scratch code stayed in the session scratchpad; no project file was changed. Amounts in rupees use 1 USD = about Rs 95 (forecast sites, 2026-10) [2nd].

## 0. Decisions

| Area | Pick | Why in one line |
|---|---|---|
| Phone login and passkeys | allauth built-ins: `phone` login method, login by code, passkey login. Add the phone later from My account, not at sign-up | Installed 65.19.7 is the latest and officially supports Django 6.1; phone OTP, optional phone and an app endpoint all ran |
| Google | allauth socialaccount, settings-based app, `AUTO_SIGNUP=False` plus the student-details form | Google returns no date of birth or consent; the DPDP flow needs both |
| SMS | MSG91 (Rs 0.25 to 0.16 per SMS) after DLT registration; Fast2SMS as the back-up | One panel for SMS, OTP, WhatsApp; Send-OTP and template APIs; the same price band as the cheapest alternative |
| Storage | Cloudflare R2, two buckets (public through a custom domain, private through short presigned URLs) | No egress fee, free CDN, 10 GB free; S3 Mumbai only for the private bucket if the privacy policy promises "India only" |
| Images | django-pictures 1.8.0 (AVIF + WebP `<picture>`), processed on the existing Celery worker | The only candidate that produces responsive AVIF/WebP markup, a DRF field and async processing |
| Email | Amazon SES ap-south-1 through Anymail, SNS to the Anymail webhook, suppression list in the database | $0.10 per 1,000 emails; Brevo's free plan stops at 300 emails a day, and every sign-up costs an email |
| Shipping | Courier-counter shipping now with tracking-URL templates; Shiprocket when daily volume justifies an API | Needs no integration; `tracking_url` already exists |
| PIN data | Offline table from the data.gov.in CSV (GODL licence) | A 1.1 s free API with no stated SLA is the wrong thing to call at checkout |
| PWA | Hand-written manifest, 30-line service worker, standalone offline page | django-pwa 2.0.1 emits an inline script the CSP blocks and is untested beyond Django 5.0 |
| SEO | Hand-written JSON-LD (Product + Book, Organization, BreadcrumbList), Open Graph, canonical; no FAQPage | Google retired FAQ rich results in May 2026 |

### Gotchas that matter most (details in the sections)
1. Phone at sign-up means two codes (phone first, then email) [ran]. Hide it there; add it from My account.
2. Do not give allauth the old free-text `User.phone`: an unverified stored number sends an SMS and stops the user at a verify step at every login until it is confirmed [ran]. Use a new verified field.
3. Password login by phone hands `get_user_by_phone` the text as typed ("98640 12345"); normalise inside it or only `+91...` works [ran].
4. allauth codes default to `WDJB-MJHT`; set a numeric 6-digit format for SMS.
5. With Redis down every rate limit lets requests through (`SoftRedisCache`); SMS costs money, so cap sends per day in the database.
6. `form-action 'self'` makes Chrome and Safari block the redirect to `accounts.google.com`; add that host.
7. boto3 1.43 + R2/B2: set `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` and `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` in the environment, not as a `client_config` object, which cannot travel through Celery's JSON.
8. The Celery worker command has no `-Q`; django-pictures sends to queue `pictures`. Set `PICTURES["QUEUE_NAME"] = "celery"`.
9. `AWS_ACCESS_KEY_ID` is used for both buckets and would also be picked up by SES; give each service its own key variables.
10. MSG91 authkeys have IP security switched on by default (error 418 from any other IP).
11. Jazzband is winding down (org archived early 2027): django-axes, model-utils, taggit, redis, widget-tweaks, simplejwt and simple-history move to new owners; watch PyPI ownership when bumping versions.

## 1. django-allauth: phone, code login, passkeys, Google, app API

### 1.1 Versions and compatibility
- `requirements.txt` pins 65.19.7, which is the latest on PyPI (changelog: 2026-10-01). Django 6.1 officially supported since 65.19.0 (2026-08-06); classifiers Django 4.2 to 6.1, Python 3.10 to 3.14; extras `fido2>=1.1.2,<3` (installed 2.2.1) [doc].
- `manage.py check` with phone login, login by code, passkey login and signup, and the Google provider all switched on, against the real project settings: no issues [ran]. `Fido2Server` builds on 3.14.2 [ran].
- History [doc]: passkeys 64.0.0 (2024-07-31), passkey signup 65.0.0, phone (SMS) authentication and `ACCOUNT_SIGNUP_FIELDS` 65.5.0 (2025-03-14), resend/change settings 65.8.0, phone fix for third-party signups 65.10.0, "trust this browser" for code login 65.13.0, RFC 8628 codes and login-code resend 65.15.0, IPv6 /64 rate-limit truncation 65.17.0, Django 6.1 65.19.0. Security fixes in 65.19.2 to 65.19.7 (TOTP enrolment limit, rate-limit race, open redirect with `ALLOWED_HOSTS=["*"]`): stay on the latest 65.19.x.

### 1.2 Phone login and verification (what ran in a scratch project)
```python
# settings.py
INSTALLED_APPS += ["allauth.socialaccount", "allauth.socialaccount.providers.google", "django.contrib.humanize"]  # humanize: WebAuthn templates
ACCOUNT_LOGIN_METHODS = {"email", "phone"}                      # "phone" here is also what lets the code form accept a number
ACCOUNT_SIGNUP_FIELDS = ["email*", "phone", "password1*", "password2*"]   # "phone" without * = optional; also creates /account/phone/verify/ and /phone/change/
ACCOUNT_LOGIN_BY_CODE_ENABLED = True                            # "Send me a sign-in code", by email and by SMS
ACCOUNT_LOGIN_BY_CODE_SUPPORTS_RESEND = True
ACCOUNT_PHONE_VERIFICATION_SUPPORTS_RESEND = True               # True = 2 resends
ACCOUNT_PHONE_VERIFICATION_SUPPORTS_CHANGE = True               # True = 2 changes of a mistyped number
ACCOUNT_PHONE_VERIFICATION_TIMEOUT = 300
ACCOUNT_PHONE_VERIFICATION_CODE_FORMAT = {"length": 6, "numeric": True, "dashed": False}   # also used for login-by-code SMS
ACCOUNT_LOGIN_BY_CODE_FORMAT = ACCOUNT_PHONE_VERIFICATION_CODE_FORMAT                      # the emailed login code
ACCOUNT_RATE_LIMITS = {"request_login_code": "5/m/ip,3/h/key", "verify_phone": "1/60s/key,10/h/ip", "change_phone": "3/h/user"}
```
Defaults [ran, read from source]: `ACCOUNT_PHONE_VERIFICATION_ENABLED` True, `_MAX_ATTEMPTS` 3, `_TIMEOUT` 900 s; login by code `_MAX_ATTEMPTS` 3, `_TIMEOUT` 180 s, `_REQUIRED` False (True forces a code on every login; or a set of `"password"`, `"mfa"`, `"socialaccount"`); rate limits `request_login_code` "20/m/ip,3/m/key", `verify_phone` "1/30s/key,3/m/ip", `change_phone` "1/m/user", `login_failed` "10/m/ip,5/300s/key". Syntax `amount/duration/per`, units s/m/h/d, `per` = ip, key or user.

Adapter, field and model (all five adapter methods are required; nothing checks at start-up, a missing one raises `NotImplementedError` at the first SMS):
```python
# accounts/fields.py
def normalise_phone(value):   # 98640 12345, 098640 12345, +91 98640 12345 -> +919864012345; None if not an Indian mobile
    m = re.fullmatch(r"(?:\+?91|0)?([6-9]\d{9})", re.sub(r"[\s\-()]", "", value or ""))
    return "+91" + m.group(1) if m else None
class IndianPhoneField(allauth.account.fields.PhoneField):       # allauth's own field wants +E.164 typed in full
    def clean(self, value):
        if not value: return super().clean(value)                # an optional field left empty must pass (bug I hit)
        if not (phone := normalise_phone(value)): raise ValidationError("Enter a 10-digit Indian mobile number.")
        return super().clean(phone)
# accounts/models.py: NOT the free-text User.phone
login_phone = models.CharField(max_length=16, blank=True)        # E.164
login_phone_verified = models.BooleanField(default=False)
# Meta.constraints: UniqueConstraint(fields=["login_phone"], condition=Q(login_phone_verified=True), name="uniq_verified_login_phone")
# accounts/adapter.py (AccountAdapter)
def phone_form_field(self, **kw): return IndianPhoneField(**kw)
def send_verification_code_sms(self, user, phone, code, **kw): queue_sms("otp", phone, {"otp": code})   # Celery task -> MSG91
def get_user_by_phone(self, phone):
    phone = normalise_phone(phone)                               # password log-in passes the text as typed
    return User.objects.filter(login_phone=phone, login_phone_verified=True).first() if phone else None
def get_phone(self, user): return (user.login_phone, user.login_phone_verified) if user.login_phone else None
def set_phone(self, user, phone, verified): user.login_phone, user.login_phone_verified = phone, verified; user.save(update_fields=[...])
def set_phone_verified(self, user, phone):                       # un-verify the number on any other account first
    User.objects.filter(login_phone=phone, login_phone_verified=True).exclude(pk=user.pk).update(login_phone_verified=False)
    self.set_phone(user, phone, True)
# send_unknown_account_sms / send_account_already_exists_sms: leave allauth's empty versions (anything else lets a stranger make you text any number)
```
Behaviour measured [ran]: typed "98640 12345" gets a 6-digit SMS and logs in; wrong code re-shows the form; unknown and unverified numbers get the same redirect and no SMS; foreign numbers are refused by the form; password login works with "+919864012345", "98640 12345" and "09864012345" once `get_user_by_phone` normalises. Sign-up without a phone goes straight to the email code; sign-up with a phone goes to the phone code first, then the email code. Popping the field in the project's `SignupForm.__init__` (`self.fields.pop("phone", None)`) ignores a posted phone: no SMS. A logged-in user adds a number at `/account/phone/change/`, receives the SMS, confirms at `/account/phone/verify/`. Edge: a second account asking for the same number within 30 s raises an uncaught `RateLimited` in `ChangePhoneView` (allauth does not catch it there); expect a 500 page and a Sentry event, rare.

Project edits needed: `field_order` and templates (`templates/account/login.html` and `signup.html` are overridden, so the new buttons do not appear by themselves: copy from allauth's login.html the `LOGIN_BY_CODE_ENABLED` button (`request_login_code_url`), the `PASSKEY_LOGIN_ENABLED` button with id `passkey_login`, `{% include "socialaccount/snippets/login.html" with page_layout="entrance" %}`, and in `extra_body` the include `mfa/webauthn/snippets/login_script.html`); `axes_username()` should also read `creds.get("phone")`; code inputs already carry `autocomplete="one-time-code"`.

SMS cost guard: allauth's limits live in the cache, which fails open here. In `queue_sms` refuse above `SMS_DAILY_CAP` counted in a small `SmsLog` table, and put Cloudflare Turnstile (free) on the sign-up and code-request forms.

### 1.3 Passkeys (WebAuthn through allauth.mfa)
```python
MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True            # button on the login page, /account/2fa/webauthn/login/
MFA_PASSKEY_SIGNUP_ENABLED = False          # later; /account/signup/passkey/
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG  # local development only
# MFAAdapter: one relying-party id for every host name (default is request.get_host(), so www. and the bare domain would not share passkeys)
def get_public_key_credential_rp_entity(self): return {"id": urlparse(settings.SITE_URL).hostname, "name": "ExamLeaf"}
```
- Passkey signup requires `ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED`, `email*` and `EMAIL_VERIFICATION="mandatory"` (system check): the project already has all three. But `SignupByPasskeyView` builds the form with `by_passkey=True`, which drops the password fields, and the project's `SignupForm.try_save` reads `self.cleaned_data["password1"]`: change to `.get`.
- A passwordless passkey login skips the MFA step (`did_use_passwordless_login`). `StaffMFAMiddleware` still demands a TOTP for staff; accept `Authenticator.Type.WEBAUTHN` there too only if staff should be allowed passkeys alone.
- CSP is fine: allauth loads `mfa/js/webauthn.js` and `account/js/onload.js` as static files and its inline blocks are `type="application/json"`. HTTPS is mandatory in production.
- Treat passkeys as an optional upgrade: Chrome on Android needs Google Play services and a screen lock; many shared family phones in Assam will not qualify.

### 1.4 Google sign-in
```python
SOCIALACCOUNT_AUTO_SIGNUP = False                     # always show our form (class, board, date of birth, parent, consent)
SOCIALACCOUNT_FORMS = {"signup": "accounts.forms.SocialSignupForm"}   # StudentDetails mixin + allauth.socialaccount.forms.SignupForm
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False            # default; an existing local account must log in once and connect Google
SOCIALACCOUNT_PROVIDERS = {"google": {"APPS": [{"client_id": env("GOOGLE_CLIENT_ID"), "secret": env("GOOGLE_CLIENT_SECRET"), "key": ""}],
                                      "SCOPE": ["profile", "email"], "OAUTH_PKCE_ENABLED": True}}
CONTENT_SECURITY_POLICY["form-action"] = [CSP.SELF, "https://accounts.google.com"]   # Chrome/Safari apply form-action to the 302 after the POST [2nd]
```
- No `django.contrib.sites` needed: with `APPS` in settings allauth needs no `SocialApp` row and no `sites` table (`SITES_ENABLED` is False without the app) [source read; the system check passes]. Run `migrate` for the socialaccount tables.
- Redirect URI (allauth is mounted at `account/`): `https://examleaf.in/account/google/login/callback/` [ran, `reverse("google_callback")`]; `http://localhost:8000/account/google/login/callback/` for development.
- Refactor `accounts/forms.py` so the extra fields, `clean_*` and `custom_signup` sit in one mixin used by `SignupForm(Mixin, AllauthSignupForm)` and `SocialSignupForm(Mixin, allauth.socialaccount.forms.SignupForm)`; both call `custom_signup`.
- What the founder creates in Google Cloud [doc]: a project, then Google Auth Platform: Branding (app name, support email, privacy-policy and home-page URLs, authorized domain `examleaf.in`; a logo triggers a light "brand verification", skip it at first); Audience = External, then "Publish app" (in Testing mode only 100 listed users and tokens expire after 7 days); Data access = only `openid`, `email`, `profile` (non-sensitive: no Google review, no user cap); Clients, "Create client", type "Web application", Authorized JavaScript origin `https://examleaf.in`, the redirect URI above (HTTPS required except localhost, paths allowed, no wildcards). Put the id and secret in `.env`.

### 1.5 Phone OTP for the mobile app (dj-rest-auth + simplejwt)
Recommendation: keep dj-rest-auth/JWT and add two thin views that run allauth's own login-by-code process in a throw-away session, exactly as `api/auth.py` already does for email codes (`email_code()`, `verification_token`). Allauth headless (`/_allauth/app/v1/auth/code/request|confirm`, `X-Session-Token`) offers the same flow, but only as a second API surface beside JWT (and it needs the `[headless]` extra since 65.13.0): worth it only if dj-rest-auth is dropped.
```python
# POST /api/v1/auth/phone/code/     {"phone": "98640 12345"} -> {"verification_token": "<session key>"}
request.session = SessionStore()
form = RequestLoginCodeForm({"phone": phone})                       # normalises, applies the request_login_code limit
if not form.is_valid() or not form.cleaned_data.get("phone"): ...400     # an empty phone is "valid" for this form
LoginCodeVerificationProcess.initiate(request=request, user=form._user, phone=form.cleaned_data["phone"])   # user None = unknown number: no SMS
request.session.save()
# POST /api/v1/auth/phone/confirm/  {"verification_token", "code"} -> the same JWT pair as /login/
request.session = SessionStore(token)
stage = LoginStageController.enter(request, LoginStageKey.LOGIN_BY_CODE.value)
process = stage and LoginCodeVerificationProcess.resume(stage)     # None when expired or the 3 attempts are used up
if not process or not compare_user_code(actual=code, expected=process.code): process and process.record_invalid_attempt(); ...400
get_adapter().set_phone_verified(process.user, process.state["phone"]); process.abort(); request.session.flush()
return jwt_encode(process.user)
```
Prototype (without DRF) behaved as intended [ran]: wrong code rejected, right code returns the user, token reuse fails, unknown number gets a token but no SMS and the same generic error, three wrong codes kill the token; through `RequestLoginCodeForm` the fourth request for one number inside a minute is refused (default `3/m/key`) and a junk number gets "Enter a 10-digit Indian mobile number." Imports come from `allauth.account.internal.*` (no stability promise, as with the existing email-code views): add a test that runs this flow so an allauth upgrade that moves them fails CI.

## 2. SMS and WhatsApp OTP providers, and DLT

| Provider | India price | Notes |
|---|---|---|
| MSG91 | SMS Rs 0.25 (5,000), 0.20 (16,500), 0.17 (60,000), 0.16 (about 1 million); "up to 0.13" custom [doc]. OTP about Rs 0.15 [2nd] | SMS, OTP, WhatsApp, email, voice in one panel; Send-OTP and template APIs; DLT hand-holding |
| Fast2SMS | Rs 0.25 (Rs 100 recharge) to 0.21 (4,000), 0.17 (14,000), 0.11 (6 lakh) [doc]. "OTP without DLT" quick route Rs 5.00 per SMS | Good back-up; the Rs 5 route is for a pilot only |
| 2Factor.in | from about Rs 0.12 to 0.16 [2nd] (official pages refused automated fetch) | `GET https://2factor.in/API/V1/<key>/SMS/+91..../AUTOGEN`, verify `.../SMS/VERIFY/<session>/<otp>` [2nd] |
| Exotel | no public price ("contact sales or dashboard") [doc] | Telephony-first, enterprise onboarding |
| Kaleyra (Tata Communications) | about Rs 0.18 [2nd] | Enterprise, longer onboarding |
| Twilio Verify | $0.05 per successful check + $0.0832 SMS to India = about Rs 12.6 per OTP [doc]; DLT Entity ID and Template ID still required [2nd] | 50 to 80 times MSG91 |
| WhatsApp (via a BSP) | Meta authentication template about Rs 0.115 per message + BSP fee + 18% GST [2nd]; Meta's page links the CSV rate card (rates effective 2026-07-01; INR billing must be migrated by 2026-12-31) [doc] | Needs a verified Meta business; do it later, as a fallback channel |

Pick MSG91. Its authkey has IP security on by default: calls from any other IP fail with error 418 [doc]; whitelist the server's outgoing IP (or the company-level list) before the first test.

HTTP shapes. Header `authkey: <key>` on every call; mobile numbers are `91XXXXXXXXXX` without `+`. The official docs site is a JavaScript app that would not load for me, so the OTP shape below comes from MSG91's help pages and API-spec mirrors [2nd]; check it against the dashboard's API tab with one test OTP.
```
# OTP: allauth generates the code, MSG91 only delivers it (otp = the value to send)
POST https://control.msg91.com/api/v5/otp?template_id=<OTP_TEMPLATE_ID>&mobile=919864012345&otp=483920&otp_expiry=5
authkey: <KEY>   Content-Type: application/json   body: {}  (optional {"Param1": ...}; variable names are case-sensitive)
-> {"type":"success","request_id":"3466..."}      HTTP 200 also on errors: test "type"
# (MSG91 can generate the code too: GET /api/v5/otp/verify?mobile=&otp= and /api/v5/otp/retry?mobile=&retrytype=text|voice; not needed here)
# Transactional template (order shipped, etc.)
POST https://control.msg91.com/api/v5/flow          (older docs: http://api.msg91.com/api/v5/flow/ with flow_id and sender)
{"template_id":"<TEMPLATE_ID>","short_url":"0","recipients":[{"mobiles":"919864012345","var1":"EL/2026-27/00012","var2":"Delhivery 1234567"}]}
-> {"type":"success","message":"<request id>"}   a template variable ##var1## is sent as var1 (case-sensitive)
# Fast2SMS equivalent [doc/2nd]: POST https://www.fast2sms.com/dev/bulkV2  authorization: <key>
{"route":"dlt","sender_id":"EXMLEF","message":"<DLT template id>","variables_values":"483920|","numbers":"9864012345"}
```
Call these from one Celery task (`ops/sms.py`, `autoretry_for=(httpx.TransportError,)`, 10 s timeout, console output when no key is set).

What the founder must do for TRAI DLT (all sources agree unless noted) [2nd, with Infobip, Telerivet, Exotel, MessageCentral and storyboard18/TRAI summaries]:
1. Register the business as a Principal Entity on one operator portal (Jio TrueConnect, Airtel, Vi VILPOWER, BSNL, MTNL); it syncs to all operators. One-time fee about Rs 5,900 including GST. Documents: business PAN, GST or TAN certificate, authorisation letter for the signatory, the signatory's government ID (LLP: add the LLP certificate or resolution). Approval 3 to 7 days; result is a 19-digit PE ID.
2. Register a header (sender ID): 6 letters, for example `EXMLEF`. Fee is reported anywhere from Rs 0 to 5,900 per header depending on source and portal: check the portal. 1 to 3 days. Since 6 May 2025 delivered headers carry `-T`, `-S`, `-P` or `-G` automatically.
3. Register content templates (free, 1 to 3 days each): exact text with `{#var#}` for variables; the carrier compares character by character and drops any deviation silently. The login OTP goes in as Transactional; order and shipping updates as Service Implicit (reaches DND numbers; no consent file). Promotions are Promotional (consent needed, 9 am to 9 pm). "Service Explicit" was abolished in May 2025 and moved to Promotional. Example: `{#var#} is your ExamLeaf verification code. It is valid for 5 minutes. Do not share it with anyone.`
4. Whitelist every URL, APK or callback number that appears inside a template (mandatory since 1 October 2024); a link to an unregistered domain gets the SMS blocked.
5. Bind the SMS provider to your PE ID as the telemarketer in the portal (the provider's panel walks through it). Since 11 December 2024 messages on unregistered PE-to-provider paths are rejected, so skip this and every OTP silently fails.
6. Enter the PE ID, header and template IDs in the MSG91 panel and copy the template ID into `.env`. Start now: the calendar time is 1 to 2 weeks and it does not depend on code.

## 3. S3-compatible media: two buckets

| | Cloudflare R2 | AWS S3 ap-south-1 (Mumbai) | Backblaze B2 |
|---|---|---|---|
| Storage | $0.015/GB-month (Rs 1.4) | $0.025/GB-month (Rs 2.4) | $6.95/TB-month (Rs 0.66/GB) |
| Egress | free | $0.1093/GB after the 100 GB/month free tier (Rs 10) | free up to 3 times the stored volume, then $0.01/GB |
| Requests | $4.50 per million writes, $0.36 per million reads | $0.005 per 1,000 PUT, $0.0004 per 1,000 GET | mostly free, small fee after a daily allowance |
| Free | 10 GB, 1 million writes, 10 million reads a month | new accounts: $200 credits for 6 months | first 10 GB |
| India region | none (hint `apac` only, fixed at creation) | yes | none |
| Public CDN | free through a custom domain; the zone must be on Cloudflare | CloudFront (more set-up) | through Cloudflare/Fastly |
| Quirks | no ACLs (a `private` ACL header is accepted and ignored [2nd]), no object lock, versioning, tagging or SSE-KMS; presigned URLs (up to 7 days) work only on `<account>.r2.cloudflarestorage.com`, never on a custom domain | full S3 | ACLs only per bucket |

[doc: Cloudflare R2 pages, Backblaze pricing page, AWS Price List files published 2026-09-16 and 09-28]

Pick R2 for both buckets. If the Privacy Policy promises that students' uploads stay in India, make only the private bucket S3 Mumbai: the same OPTIONS minus `endpoint_url`, with `region_name="ap-south-1"`, Block Public Access on, ACLs disabled. Move DNS to Cloudflare (free plan) for `media.examleaf.in`.

django-storages: 1.14.6 (2025-04-02) is the latest release; there is no 1.15. Its classifiers stop at Django 5.1 and Python 3.12 and the main branch has had commits since (2026-08-02) but no release [doc]. It works here: `S3Storage` plus signed URLs on Django 6.1.2 / Python 3.14.2 / boto3 1.43.109, and a moto end-to-end save, exists, url, collision-rename and django-pictures run [ran]. Pin 1.14.6 and keep a moto test in CI.
```python
_s3 = {"endpoint_url": env("S3_ENDPOINT_URL", default=None),     # R2: https://<ACCOUNT_ID>.r2.cloudflarestorage.com ; AWS: unset
       "region_name": env("S3_REGION", default="auto"),          # R2 "auto"; AWS "ap-south-1"
       "access_key": env("S3_ACCESS_KEY_ID", default=None), "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
       "file_overwrite": False, "default_acl": None}              # never set an ACL: R2 ignores it, new AWS buckets (ACLs disabled by default) can reject it
if env("MEDIA_BUCKET", default=""):
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage",     # PRIVATE: answer sheets, invoices, credit notes
        "OPTIONS": {**_s3, "bucket_name": env("MEDIA_BUCKET"), "querystring_auth": True, "querystring_expire": 300}}
    STORAGES["public"] = {"BACKEND": "storages.backends.s3.S3Storage",      # product images, through the CDN domain
        "OPTIONS": {**_s3, "bucket_name": env("PUBLIC_MEDIA_BUCKET"), "custom_domain": env("PUBLIC_MEDIA_DOMAIN"),   # media.examleaf.in
                    "querystring_auth": False, "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"}}}
else:
    STORAGES["public"] = dict(STORAGES["default"])                          # development and tests
# environment: AWS_REQUEST_CHECKSUM_CALCULATION=when_required  AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
# models: FileField(storage=...) takes a callable, not an alias string, and makemigrations needs it importable (no lambda)
def public_storage(): return storages["public"]
```
Measured [ran]: the private URL is signed with `X-Amz-Expires=300`; the public URL is `https://media.examleaf.in/products/a.jpg` with no query string and the object carries the `CacheControl`; a second save of the same name becomes `a_iesJbhF.jpg`, so the immutable header is safe. Also: add `https://media.examleaf.in` to CSP `img-src`; the backup bucket keeps working (give it its own key variables); strip EXIF (GPS) and cap pixel size when the answer-sheet upload is built; keep serving invoices through the existing `FileResponse(default_storage.open(...))` or redirect to `storage.url(name, expire=60)` after the permission check.

## 4. Image variants (WebP/AVIF, responsive)

| Library | Latest | Tags | What you get | Verdict |
|---|---|---|---|---|
| django-pictures 1.8.0 | 2026-09-22, active (release every 1 to 2 months) | Django 5.2/6.0, Python 3.10 to 3.14; needs Pillow 11.3+ | `PictureField`, `{% picture %}` with AVIF/WebP `srcset`+`sizes`, aspect ratios, DRF field, async, migration operation | pick |
| sorl-thumbnail 13.1.0 | 2026-08-19 | Django 5.2/6.0/6.1, Python to 3.14 | `{% thumbnail ... format="WEBP" %}`, one size per tag, key-value table, builds in the request | fallback |
| django-imagekit 6.1.1 | 2026-09-15 | Python to 3.14, no Django tags | `ImageSpecField(format="WEBP")`, one spec per size, checks storage on each render | fallback |
| easy-thumbnails 2.10.1 | 2025-08-17 | Django to 5.2 | aliases; stale; left Jazzband | skip |

All four import and build WebP and AVIF on Django 6.1.2 / Python 3.14.2 / Pillow 12.3.0 [ran]. Pillow 12.3.0's Linux wheel (manylinux x86_64, cp314) bundles libavif and libwebp, so the Docker image needs no extra package [ran]. Encoding costs 60 to 250 ms per variant (AVIF about 25% smaller than WebP on a synthetic image); django-pictures made 24 variants of one 1200x1800 JPEG in 4.0 s [ran], so processing must leave the request.
```python
INSTALLED_APPS += ["pictures"]
PICTURES = {"FILE_TYPES": ["AVIF", "WEBP"],   # <source> order: the browser takes the first it supports
            "BREAKPOINTS": {"s": 576, "m": 992, "l": 1200}, "GRID_COLUMNS": 12, "CONTAINER_WIDTH": 1200, "PIXEL_DENSITIES": [1, 2],
            "QUEUE_NAME": "celery",           # the worker runs without -Q, so it only reads the default queue
            "PROCESSOR": "pictures.tasks.celery_process_picture", "USE_PLACEHOLDERS": False}
cover = PictureField(upload_to="products/", storage=public_storage, aspect_ratios=["2/3"], blank=True,
                     width_field="cover_width", height_field="cover_height",   # without them every .width opens the file in S3
                     validators=[MaxSizeValidator(4096, 4096)])                # plus two PositiveIntegerField(null=True, editable=False)
{% load pictures %}{% picture product.cover img_alt=product.title img_loading="lazy" ratio="2/3" s=6 m=4 l=3 %}
```
Gotchas: on Django 6 the default processor is Django Tasks on a queue named `pictures` and import fails (`ImproperlyConfigured`) unless `TASKS` lists it; Django ships only the immediate and dummy backends, so that default would run inside the request. The built-in Celery processor works but warns (`PendingDeprecationWarning`) and is scheduled for removal when Django 5.2 LTS support ends (2028); the replacement is a 10-line `@shared_task` taking the same keyword arguments (`storage, file_name, sender, new, old`). The storage definition travels through the broker as JSON [ran: `deconstruct()` of both storages is JSON-clean], hence no `client_config=Config(...)` in OPTIONS. Swapping the existing `ImageField`s uses the package's `AlterPictureField` in the migration, which queues processing of existing covers. `img_url` (single-size URLs) only offers file types listed in `FILE_TYPES`.

## 5. Email: ESP, bounce and complaint webhooks, suppression

- Anymail 15.2 (2026-09-05, Django 5.0 to 6.0 tags, `django>=5.0`) [doc]. Add `path("anymail/", include("anymail.urls"))`. The webhook views are `csrf_exempt` and `login_not_required`. Their only protection is HTTP basic auth: `ANYMAIL_WEBHOOK_SECRET=user:pass` (settings.py already turns `ANYMAIL_*` variables into the `ANYMAIL` dict; a list of several `user:pass` allows rotation; no signatures are checked for SES, Brevo or Postmark) [ran, source]. Give the ESP `https://user:pass@examleaf.in/anymail/<esp>/tracking/` with `<esp>` = `amazon_ses`, `brevo` or `postmark`. Caddy needs no rule for `/anymail/` (it only restricts `/health/`).
- Signal `anymail.signals.tracking(event, esp_name)`; `event.event_type` in `bounced|complained|rejected|failed|deferred|delivered...`, `event.reject_reason` in `bounced|invalid|blocked|spam`, `event.recipient`, `event.esp_event` (raw). An exception in a receiver answers 400 and the ESP retries: keep the receiver tiny. `anymail.signals.pre_send` may raise `AnymailCancelSend` to stop a message [ran, source].
- Amazon SES [doc]: `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend`; SES configuration set with an SNS event destination (same region) for Send, Delivery, Bounce, Complaint, Reject (leave Open/Click off); SNS topic with an HTTPS subscription to the Anymail URL; Anymail confirms it itself (`AMAZON_SES_AUTO_CONFIRM_SNS_SUBSCRIPTIONS`, default True, needs `WEBHOOK_SECRET` set first and `sns:ConfirmSubscription` on the IAM user); `ANYMAIL["AMAZON_SES_CONFIGURATION_SET_NAME"]`; region and keys through `AMAZON_SES_CLIENT_PARAMS` (a dict: set it in settings.py, not through a flat environment variable, and use SES's own key variables, not `AWS_ACCESS_KEY_ID`). Bounce mapping: `event.description` is "Permanent: General" or "Transient: MailboxFull".
- Brevo [doc]: Transactional, Email, Settings, Webhook; maps `hard_bounce` and `soft_bounce` both to bounced (read `esp_event["event"]`), `spam`/`complaint` to complained, `blocked` to rejected; events can arrive out of order; no request signing. Postmark [doc]: Server, Settings, Webhooks; `HardBounce`/`SoftBounce` in `esp_event["Type"]`, no "sent" event.
- Suppression in Django (about 25 lines): 
```python
class EmailSuppression(models.Model):    # email lower-cased, unique; reason hard_bounce|complaint|invalid; source; created
@receiver(tracking)
def remember(sender, event, esp_name, **kw):
    soft = (event.description or "").startswith("Transient") or (event.esp_event or {}).get("event") == "soft_bounce" or (event.esp_event or {}).get("Type") == "SoftBounce"
    if event.event_type == "complained" or (event.event_type in ("bounced", "rejected") and event.reject_reason in ("bounced", "invalid") and not soft):
        EmailSuppression.objects.get_or_create(email=event.recipient.lower(), defaults={...})
@receiver(pre_send)
def skip(sender, message, esp_name, **kw):
    message.to = [a for a in message.to if not EmailSuppression.objects.filter(email=a.lower()).exists()]
    if not (message.to or message.cc or message.bcc): raise AnymailCancelSend()
```
Register it in the admin so staff can delete a wrongly suppressed student. SES also keeps an account-level list on its own (on by default for accounts opened after 2019-11-25; hard bounces and complaints only; Gmail sends no complaint data; suppressed sends still count against the quota) [doc].
- India choice: SES Mumbai. $0.10 per 1,000 emails à la carte (Rs 9.5), new AWS accounts get $200 credits for 6 months [doc]. A new account starts in the sandbox (verified recipients only, 200 messages a day, 1 per second); the production-access request is answered within about 24 hours and asks for the website URL and bounce handling [doc]. Brevo: free 300 emails a day, Starter $9 a month [2nd]; a launch-day spike above 300 sign-ups locks students out because every sign-up is an emailed code. Postmark: $15 for 10,000 a month [doc], strict approval, no India angle. Keep Brevo only for the first test weeks (DEPLOYMENT.md uses it today).
- DNS for `examleaf.in` [doc/2nd; the SES console shows the exact values]: three Easy DKIM CNAMEs (`<token>._domainkey` to `<token>.dkim.amazonses.com`); a custom MAIL FROM subdomain (`mail.examleaf.in`: MX `10 feedback-smtp.ap-south-1.amazonses.com`, TXT `v=spf1 include:amazonses.com ~all`) so SPF aligns; `_dmarc` TXT `v=DMARC1; p=none; rua=mailto:dmarc@examleaf.in`, moved to `quarantine` after two to four clean weeks of reports.

## 6. Shipping: Shiprocket and Delhivery

Start-simple answer: yes, a tracking-URL template per courier is enough to start. `ship_order()` already takes a `tracking_url`; fill it from a dict when the admin leaves it blank.
```python
TRACKING_URLS = {   # answered HTTP 200 with a dummy number on 2026-10-08; open one real AWB in a browser before trusting each
    "delhivery": "https://www.delhivery.com/track-v2/package/{awb}",
    "blue dart": "https://www.bluedart.com/trackdartresult?trackFor=0&trackNo={awb}",
    "ekart":     "https://ekartlogistics.com/shipmenttrack/{awb}"}
FALLBACK = "https://t.17track.net/en#nums={awb}"      # India Post, DTDC, Xpressbees and the rest
```
India Post's page needs a CAPTCHA and I found no deep link that works (a blog's `/track-result/article-number/<no>` returned 404 to curl); I found no stable deep-link parameter for DTDC or Xpressbees either (old DTDC URLs now redirect to dtdc.com/in/). Show the number and the 17TRACK link for them.

Move to an API when daily volume or the support load justifies it (rule of thumb from aggregator guides [2nd]: about 30 to 50 parcels a day, or when you want automatic "delivered", NDR and RTO statuses). Choose the aggregator first: Shiprocket gives 15 to 25 couriers with no minimum order; a direct Delhivery contract pays off from about 500 orders a month [2nd].

| | Shiprocket [doc/2nd: apidocs.shiprocket.in returned 502, so via support articles and integrators] | Delhivery [doc: public readme.io docs] |
|---|---|---|
| Account | KYC at Shiprocket; create a separate API user (Settings, Company, API) | Delhivery One account or sales contact; token in the account header; pickup warehouse name (case-sensitive) |
| Auth | `POST https://apiv2.shiprocket.in/v1/external/auth/login` {email, password} returns a token valid 240 hours (10 days); `Authorization: Bearer <token>` | `Authorization: Token <token>` (public docs call the token the only credential); staging `https://staging-express.delhivery.com`, production `https://track.delhivery.com` |
| Order | `POST /v1/external/orders/create/adhoc` returns `order_id`, `shipment_id` | `POST /api/cmu/create.json` body `format=json&data=<json>` with `shipments[]` and `pickup_location{name,add,pin,phone}`; `seller_gst_tin` and `hsn_code` are marked mandatory (ExamLeaf's GSTIN may be empty: ask Delhivery) |
| AWB, pickup | `POST /courier/assign/awb`, `POST /courier/generate/pickup`, `POST /courier/generate/label` | AWB made with the order (or `fetch waybill`); pickup-request API; packing-slip API |
| Tracking | `GET /courier/track/awb/{awb}`; webhook | `GET /api/v1/packages/json/?waybill=...` (750 requests per 5 minutes per IP); push webhook needs Delhivery to set it up (5 to 6 working days, they want 1 to 2 live waybills to test) |
| Webhook | Settings, API, Webhooks: POST JSON, security token arrives as header `x-api-key`, must answer 200, URL must not contain "shiprocket", "kartrocket", "sr" or "kr" [2nd] | share the endpoint and any auth header with Delhivery; expects 200 |

Integration shape when the time comes: `shop/shipping.py` with `create_shipment(order)`, `track(awb)`, and one webhook view that maps courier statuses to the existing shipped/delivered transitions, using the existing `WebhookEvent` table for idempotency (as the Razorpay webhook does). Do not build both couriers. Shipments above Rs 50,000 need an e-way bill.

## 7. PIN codes

- `api.postalpincode.in/pincode/{pin}`: free, no key, JSON with `Status`, post offices, `District`, `State`, `Circle`; "no records" still answers HTTP 200 with `Status: Error`. I called it 3 times today (the two timings I captured: 1.1 s and 1.2 s); I found no owner, SLA, terms or rate limit [ran].
- Official data: data.gov.in "All India Pincode Directory (till last month)", Department of Posts, monthly, CSV about 157,000 post-office rows and 15.6 MiB, columns `circlename, regionname, divisionname, officename, pincode, officetype, delivery, district, statename, latitude, longitude`; Government Open Data Licence India (free for commercial use, attribution required) [2nd: mirrors and listings; data.gov.in refused automated fetch with 403, so I did not download it]. Collapse to the unique PINs (a December 2021 snapshot counted about 19,300 [2nd]). API resource id `04cbe4b1-2f2b-4c39-a1d5-1c2e28bc0e32` ("through web service", free API key).
- Recommendation: ship an offline table. Founder downloads the CSV once at https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month (free sign-in); a management command `import_pincodes <csv>` builds `PinCode(pin primary key, state code, districts JSON)` (map `statename` to `localflavor.in_.in_states` codes and fail the import on an unmapped name; keep a set of states per PIN because a few PINs straddle borders). Use it for: auto-filling district and state in the address form; rejecting a state that does not match the PIN (it decides CGST+SGST versus IGST); `validate_pin` that knows real PINs. Refresh yearly by hand. Keep the call to `api.postalpincode.in` only as a fallback for a PIN missing from the table. Courier serviceability and COD availability per PIN is a separate call (Shiprocket serviceability or Delhivery pin-codes API), cached for a day.

## 8. PWA

- django-pwa 2.0.1 (2024-09-27; Django tags stop at 5.0; repository active, no release since) [ran: wheel inspected]. Its `pwa.html` template renders an inline `<script>` that registers the service worker: the project's `script-src 'self'` blocks it. Its default worker pre-caches 19 icon and splash images and answers every GET from the cache first, with the offline page for any failure. Hand-writing is smaller than adapting it.
- Installability [doc, MDN]: Chrome needs a manifest with `name` or `short_name`, 192 and 512 px icons, `start_url`, `display`, and HTTPS; a service worker is not required. iOS Safari installs through Share, Add to Home Screen and has no install-prompt event; Firefox desktop does not install.
- Files: `manifest` view (`JsonResponse(..., content_type="application/manifest+json")` with `id "/"`, `start_url "/?source=pwa"`, `scope "/"`, `display "standalone"`, `theme_color "#0b2a5b"` as in base.html, icons 192, 512 and a maskable 512, built with `static()` so hashed names are right); `/sw.js` served from the site root (scope `/`) by a `TemplateView` with `Cache-Control: no-cache`; `static/js/pwa.js` containing `if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("/sw.js"))`, loaded with `<script src defer>`; in base.html `<link rel="manifest" href="{% url 'manifest' %}">`.
```js
// templates/sw.js, rendered per release so the hashed CSS name and CACHE change with every deploy
const CACHE = "examleaf-{{ release }}", PRECACHE = ["/offline/", "{% static 'css/site.css' %}", "{% static 'img/favicon.svg' %}"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;                          // never POSTs, never other origins
  if (r.mode === "navigate") return e.respondWith(fetch(r).catch(() => caches.match("/offline/")));   // pages: network only, offline page on failure
  if (u.pathname.startsWith("/static/")) e.respondWith(caches.match(r).then(hit => hit || fetch(r).then(res => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(r, copy)); } return res; })));   // clone before the body is read
});
```
- The offline page must be a standalone template that does not extend `base.html`: the install-time fetch carries the visitor's cookies, so a cached copy of the normal layout would hold their menu and a CSRF token. Never cache HTML pages, `/account/`, `/shop/`, `/api/` or `/s/` (gated solutions would outlive a log-out); that also keeps `PrivatePagesMiddleware`'s promise.
- CSP: no script change needed (same-origin files). Add `manifest-src 'self'` and `worker-src 'self'` for clarity, and later the media domain to `img-src`. I did not test the worker in a browser: check DevTools, Application, for CSP errors.

## 9. SEO

- Google changelog [doc]: FAQ rich results were deprecated in May 2026 and no longer show, so skip FAQPage markup (keep the visible FAQ for readers); Book actions were deprecated in June 2025 (they were for lending and reading partners, not sellers); merchant return-policy markup moved to its own page in June 2025 and shipping-policy markup arrived in November 2025; the sitelinks search box is gone. Still supported: Product (snippets and merchant listings), Organization, Breadcrumb, Review snippet.
- Product page [doc]: required `name`, `image`, `offers` (`price`, `priceCurrency`, `availability`, `url`, `itemCondition`); for merchant listings add `shippingDetails` and `hasMerchantReturnPolicy`; identifiers `gtin13` (an ISBN-13 is a GTIN-13), `isbn`, `sku`, `brand`. Google's page does not discuss typing a product as `["Product","Book"]`: emit it, run the Rich Results Test, and fall back to `Product` with `isbn` if it complains. Add `aggregateRating` only from real approved reviews. A free Merchant Center product feed (a view producing XML from `Product`) adds Google Shopping free listings.
- Hand-written, not django-meta 2.5.1 (2026-02-17, Django 6.0 tag): it builds Open Graph/Twitter tags and microdata but not a JSON-LD graph, and base.html has no OG, canonical or JSON-LD blocks yet (`{% block extra_head %}` exists).
```python
# shop/templatetags/seo.py: the script type is a data block, so script-src does not apply (not tested in a browser); escape for "</script>"
@register.simple_tag
def jsonld(data):
    s = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(f'<script type="application/ld+json">{s}</script>')
# Product.jsonld(request): {"@context": "https://schema.org", "@type": ["Product", "Book"], "name", "image": [absolute URLs], "description", "sku",
#   "isbn", "gtin13": isbn.replace("-", ""), "bookFormat": "https://schema.org/Paperback", "numberOfPages", "inLanguage", "brand": {"@type": "Brand", "name": "ExamLeaf"},
#   "offers": {"@type": "Offer", "url", "priceCurrency": "INR", "price": "245.00", "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/NewCondition",
#              "seller": {"@type": "Organization", "name": "ExamLeaf LLP"}, "shippingDetails": {OfferShippingDetails}, "hasMerchantReturnPolicy": {MerchantReturnPolicy}}}
# site-wide on the home page: Organization (name, legalName, url, logo, email, telephone, address, sameAs); BreadcrumbList on product pages
```
- Open Graph: `og:type`, `og:title`, `og:description`, `og:url`, `og:image` (1200x630), `twitter:card=summary_large_image`, `<link rel="canonical">`. For the image: a static `og-default.jpg` for the site, and per product a JPEG composite made by a small Celery task with Pillow on `Product` save (cover on a brand-colour 1200x630 canvas, title in a bundled OFL font, saved to `storages["public"]` as `og/<slug>.jpg`; English titles need nothing extra, Assamese shaping needs Raqm and FriBiDi, not tested on Linux). JPEG, not WebP/AVIF, because not every crawler reads the newer formats.

## 10. Other things a real Indian D2C publisher site still lacks (simplest approach)

- Abandoned-cart email: one Celery beat task over `Cart.modified` (3 to 48 h, items, verified email, no order since) plus a `reminded_at` field and a one-click unsubscribe; no discount. Skip students under 18: DPDP Act s. 9(3) bars tracking, behavioural monitoring and targeted advertising aimed at children, and parental consent does not lift it (Act text; same reading in `docs/examleaf-platform-plan.md`).
- Order SMS (placed, shipped with tracking, delivered): the same `ops/sms.py`, Service-Implicit templates, called from `shop.services.notify()` next to the email; only with a verified number.
- Review moderation: a `Review` model (pending, approved, rejected), only from buyers of a delivered order, one per product and user, approve in the admin (simple-history already audits); honeypot plus allauth-style rate limit.
- Gift and bulk school orders with a quotation: a request form (school, GSTIN checked with `stdnum.in_.gstin`, items, delivery PIN), a quotation PDF from the existing WeasyPrint invoice pipeline (valid 15 days), payment by a Razorpay Payment Link or NEFT/UPI against a proforma, order entered by staff through `create_order`; gift = a message plus "no prices on the packing slip" flags.
- Wholesale for booksellers: a BOOKSELLER role (roles are groups already), a discount percentage per account, GSTIN required, minimum quantity, advance payment first; the bill-of-supply versus tax-invoice logic already exists.
- Serviceability and delivery estimate at checkout: the PIN table plus a cached courier pin-code call (section 7).
- RTO, NDR and COD refusals: wait for courier webhooks; then add statuses and a refusal counter that disables COD for repeat refusers.
- Back-in-stock and low-stock alerts: a `StockAlert(email, product)` row and a signal on stock going 0 to above 0; a beat task that mails the SALES role below a threshold.
- Bot and SMS-pumping protection: Cloudflare Turnstile on sign-up, code requests, contact and coupon forms (server check `POST https://challenges.cloudflare.com/turnstile/v0/siteverify`; its script and frame need CSP entries); the database SMS cap from section 1.2.
- Cloudflare proxy in front (free: DDoS, WAF, cache): do it after launch, then change `PROXY_COUNT` and Caddy's trusted proxies so axes, allauth and DRF still see the real client address.
- Analytics: a cookieless tool (Plausible or self-hosted Umami), no ad pixels for minors; add its host to CSP.
- Search: PostgreSQL full text (`django.contrib.postgres.search`, `pg_trgm`); no Elasticsearch.
- GST for the CA: a management command exporting GSTR-1 style CSV (B2C by state and rate, HSN summary, credit notes) from `Invoice` and `CreditNote`; e-invoicing (IRN) only above the turnover threshold (Rs 5 crore as far as I remember, not fetched: confirm with the CA); e-way bill above Rs 50,000 per consignment.
- Printed QR codes outlive the site: register `examleaf.in` for 10 years with auto-renew, registrar lock and a spare domain that redirects; keep Postgres point-in-time recovery (WAL archiving to R2) on the list because daily dumps mean up to 24 hours of lost orders.
- Supply chain: Jazzband (django-axes, model-utils, taggit, django-redis, widget-tweaks, simplejwt; simple-history has already moved) is winding down, with PyPI ownership moving to project leads through December 2026 and the organisation archived in early 2027 [doc]: keep the pins, enable Dependabot, and look at who publishes each bump.
- Parent's confirmation link by SMS: in rural Assam a parent's mobile reaches more people than email, and `parent_contact` already accepts a phone, so SMS is a good delivery channel for the `PARENTAL_CONSENT_MODE=verified` link. It is not by itself a verifiable-consent route: rule 10 of the DPDP Rules 2025 lists reliable identity and age details already held by the fiduciary, or details or a virtual token from an authorised entity (DigiLocker type), and `docs/examleaf-platform-plan.md` reads it the same way (no OTP route).

## 11. Suggested order of work
1. This week, in parallel with code: start DLT registration (entity, header, OTP and order templates) and the Google Cloud and SES accounts; they take calendar time.
2. Storage split on R2 + `PUBLIC_MEDIA_DOMAIN`, django-pictures, OG/JSON-LD tags, the CSP additions.
3. SES + Anymail webhook + suppression list; DKIM/DMARC records.
4. Phone login: new fields, adapter, field, templates, `ops/sms.py`, SMS cap, then the two app endpoints.
5. Passkey login (settings, template includes, relying-party id), then Google.
6. PIN table and checkout validation; tracking-URL templates.
7. PWA. Shiprocket and the order-SMS/abandoned-cart/review items when orders justify them.

## 12. Not verified, and caveats
- MSG91's official docs site and Shiprocket's `apidocs.shiprocket.in` would not load (SPA, 502): their API shapes and Shiprocket's 240-hour token and webhook rules come from help pages, integrators and mirrors [2nd]. Test each with one real call before coding.
- Delhivery's `Authorization: Token ...` header text is not in the public docs I could read; Delhivery's webhook set-up and direct-account terms need their contact.
- DLT header and template fees differ between sources (Rs 0 to 5,900); Meta's INR rates, Brevo's plans and 2Factor/Kaleyra/Exotel prices are from secondary pages.
- data.gov.in blocked automated fetch: the CSV's size, row count and column names are from listings and mirrors; nothing was downloaded.
- Not run against real R2/B2 (only moto), not run in a browser (service worker, passkeys, Google redirect, CSP `form-action` behaviour), not run against real MSG91 or SES.
- The e-invoicing threshold and the Turnstile endpoint are from memory, not fetched; DPDP s. 9(3) and rule 10 were read in the Act and Rules text files that earlier research runs left in the session scratchpad, and match `docs/examleaf-platform-plan.md`. None of this is legal advice.

## Sources (all read on 2026-10-08)
Pages marked [2nd] in the text, and the entries for content-security-policy.com, the Blender commit, ClickPost, support.shiprocket.in, mailinabox and Brevo's plans, were read through WebSearch result summaries rather than a direct fetch. Pages that returned 403, 404 or 502 are named in section 12 and are not relied on.
- allauth: https://docs.allauth.org/en/latest/account/phone.html ; /account/configuration.html ; /mfa/configuration.html ; /mfa/webauthn.html ; /socialaccount/configuration.html ; /socialaccount/providers/google.html ; https://raw.githubusercontent.com/pennersr/django-allauth/main/ChangeLog.rst ; .../docs/release-notes/2025.rst and 2024.rst ; https://pypi.org/pypi/django-allauth/json ; the installed 65.19.7 source in the project's `.venv`.
- Google: https://support.google.com/cloud/answer/15549945 ; /13463073 ; https://developers.google.com/identity/protocols/oauth2/web-server ; CSP form-action and redirects: https://content-security-policy.com/form-action , https://projects.blender.org/archive/phabricator/commit/94d340fcffab6642e9ddc2e51dfa1a95f76f2c35
- SMS: https://msg91.com/in/pricing/sms ; https://msg91.com/help/api/where-can-i-find-my-authentication-ke ; https://msg91.com/help/api/what-do-you-mean-by-api-security ; https://api.msg91.com/apidoc/textsms/send-sms-flow.php ; https://www.withone.ai/knowledge/msg91/conn_mod_def%3A%3AGNWEPXHtmnI%3A%3Aq4wrVJxbTKqbNHKe5PcQVw ; https://www.rubydoc.info/gems/msg91/Msg91/Otp ; https://jentic.com/apis/msg91.com/msg91.md ; https://www.fast2sms.com/Bulk-SMS-Price ; https://www.fast2sms.com/OTP-SMS-via-API-without-DLT-Registration ; https://www.fast2sms.com/help/?p=17046 ; https://www.twilio.com/en-us/verify/pricing ; https://www.twilio.com/en-us/sms/pricing/in ; https://developer.exotel.com/docs/sms-support/sms-pricing ; https://www.messagecentral.com/blog/sms-otp-pricing-india (a competitor's article) ; https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing.md ; https://baat.ai/blog/whatsapp-api-pricing-india
- DLT/TRAI: https://www.telerivet.com/blog/india-sms-compliance-trai-dlt-registration-and-tcccpr-guide ; https://www.infobip.com/docs/essentials/dlt-registration ; https://support.exotel.com/support/solutions/articles/3000101739-company-entity-registration-on-operator-portal ; https://www.storyboard18.com/digital/trai-implements-traceability-framework-for-commercial-sms-aims-to-combat-spam-enhance-consumer-trust-51109.htm ; https://www.storyboard18.com/how-it-works/why-your-sms-now-looks-like-a-code-trais-new-message-format-explained-70270.htm ; https://msg91.com/help/dlt-registration-in-india/dlt-template-scrubbing-filtering-rules
- Storage: https://developers.cloudflare.com/r2/api/s3/api/ ; /r2/pricing/ ; /r2/buckets/data-location/ ; /r2/buckets/public-buckets/ ; /r2/api/s3/presigned-urls/ ; https://raw.githubusercontent.com/jschneier/django-storages/master/docs/backends/s3_compatible/cloudflare-r2.rst and backblaze-B2.rst ; https://api.github.com/repos/jschneier/django-storages/commits ; https://pypi.org/pypi/django-storages/json ; https://www.backblaze.com/cloud-storage/pricing ; AWS Price List https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/ap-south-1/index.json and .../AWSDataTransfer/current/ap-south-1/index.json ; boto3 1.36 checksum change: https://discourse.mailinabox.email/t/warning-using-boto3-1-36-0-may-result-in-errors/16180
- Images: https://pypi.org/pypi/django-pictures/json (and django-imagekit, sorl-thumbnail, easy-thumbnails, pillow 12.3.0) ; https://raw.githubusercontent.com/codingjoe/django-pictures/main/README.md ; django-pictures 1.8.0 wheel (code read) ; GitHub repository metadata for the four libraries.
- Email: https://anymail.dev/en/stable/sending/tracking/ ; /esps/amazon_ses/ ; /esps/postmark/ ; /esps/brevo/ ; https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html ; https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html ; https://aws.amazon.com/ses/pricing/ ; https://postmarkapp.com/pricing ; Brevo plans via search summaries (brevo.com/pricing did not render).
- Shipping: https://www.shiprocket.in/knowledgebase/shiprocket-api-document-helpsheet/ ; https://support.shiprocket.in/support/solutions/articles/43000337456 ; https://clickpost.freshdesk.com/support/solutions/articles/43000722537-how-to-configure-webhooks-for-shiprocket ; https://delhivery-express-api-doc.readme.io/llms.txt ; .../reference/order-creation-api.md ; .../order-tracking-api.md ; .../tracking-via-push-api-webhook-1.md ; https://help.delhivery.com/docs/client-developer-portal-1 ; https://support.aftership.com/en/shipping/articles/15380723-delhivery-developer-guide-api-credentials ; tracking pages probed with curl: delhivery.com, bluedart.com, ekartlogistics.com, 17track.net, indiapost.gov.in, dtdc.com, xpressbees.com
- PIN: https://api.postalpincode.in/pincode/781001 (called) ; https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month ; https://aikosh.indiaai.gov.in/home/datasets/details/all_india_pincode_directory_till_last_month_1.html ; https://ndp.ckan.civicdatalab.in/dataset/all-india-pincode-directory ; https://github.com/harshvardhaniimi/IndiaPIN
- PWA and SEO: https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable ; https://pypi.org/pypi/django-pwa/json ; https://github.com/silviolleite/django-pwa ; https://developers.google.com/search/updates ; https://developers.google.com/search/docs/appearance/structured-data/search-gallery ; /faqpage ; /product ; https://pypi.org/pypi/django-meta/json
- Other: https://jazzband.co/news/2026/03/14/wind-down-plan ; USD/INR from https://coincodex.com/forex/usd-inr/forecast (forecast, approximate)
