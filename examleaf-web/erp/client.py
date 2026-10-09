"""ERPNext's API for the platform's integration account (provider "erpnext"; its credentials {api_key, api_secret,
base_url} and, when the base URL is the cluster's service rather than the site, site_name), on the integrations
client: the call log, the circuit breaker, and its failures as IntegrationUnavailable (unreachable, 429 with its
Retry-After, 5xx), IntegrationRejected (examleaf_erp's 400, 404, 409, 422) and IntegrationAuthFailed (Frappe's 401
and 403, or the app's 403 permission_denied). A refusal of examleaf_erp's carries its `code` and `field` on the
exception (None for one of Frappe's own, before the method ran). With ERP_MODE=fake the calls go to the in-memory
double (fake.py) instead of the network."""

from django.conf import settings

from integrations.client import Client, IntegrationError
from integrations.models import IntegrationAccount

from . import contract


class ErpClient(Client):
    def __init__(self, account, transport=None, force=False):
        super().__init__(account, transport=transport, force=force)
        self.credentials = account.get_credentials()
        self.base_url = (self.credentials.get("base_url") or contract.FAKE_URL).rstrip("/")

    def headers(self):
        key, secret = self.credentials.get("api_key", ""), self.credentials.get("api_secret", "")
        headers = {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}
        if site := self.credentials.get("site_name"):
            headers[contract.SITE_HEADER] = site
        return headers

    def body_error(self, response, data):
        return contract.refusal(data)

    def call(self, method, payload):
        """A method of examleaf_erp.api: what it answered (Frappe's envelope unwrapped)."""
        try:
            return contract.unwrap(self.request("POST", contract.method_path(method), operation=method, json=payload))
        except IntegrationError as error:
            explain(error, method)
            raise

    def get_doc(self, doctype, name):
        """A document read again through Frappe's REST: its fields, or {} when it is gone (404)."""
        try:
            data = self.request("GET", contract.resource_path(doctype, name), operation=f"read {doctype}")
        except IntegrationError as error:
            if error.status_code == 404:
                return {}
            explain(error, f"read {doctype}")
            raise
        return (data or {}).get("data") or {}


def explain(error, operation):
    """The refusal in its own words as the exception's message, and examleaf_erp's code and field on it (`code`,
    `field`: None for a refusal of Frappe's own, before the method ran)."""
    refused = contract.error_of(error.data)
    error.code = refused.get("code") if refused else None
    error.field = refused.get("field") if refused else None
    if detail := contract.describe(refused) if refused else contract.frappe_error(error.data):
        status = f"HTTP {error.status_code}" if error.status_code else "no answer"
        error.args = (f"{error.account} {operation}: {status}: {detail}",)


def transport():
    """The in-memory ERPNext of ERP_MODE=fake (development and the tests), else the network."""
    if settings.ERP_MODE == "fake":
        from .fake import FAKE

        return FAKE.transport()
    return None


def client(account=None, force=False):
    """The client of the enabled ERPNext account (or of `account`), or None while there is none."""
    account = account or IntegrationAccount.enabled_for("erpnext")
    return ErpClient(account, transport=transport(), force=force) if account else None


def connection_test(account):
    """The account's connection test (integrations.services.CONNECTION_TESTS): examleaf_erp's ping."""
    answer = client(account, force=True).call("ping", {})
    site = answer.get("name") if isinstance(answer, dict) else ""
    versions = answer.get("versions", {}) if isinstance(answer, dict) else {}
    version = f", examleaf_erp {versions['examleaf_erp']}" if versions.get("examleaf_erp") else ""
    return f"Connected: ERPNext answered the ping ({site or 'its site'}{version})."
