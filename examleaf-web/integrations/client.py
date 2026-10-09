"""The base HTTP client of a provider's API: httpx with a connect and a read timeout (INTEGRATIONS_CONNECT_TIMEOUT,
INTEGRATIONS_READ_TIMEOUT), each request logged (IntegrationCall, redacted) and counted by the account's circuit
breaker, and its failure turned into one of three exceptions: IntegrationUnavailable (unreachable, too slow, 429,
5xx: try again later; CircuitOpen when no call was made), IntegrationRejected (the provider answered and refused,
also inside a 2xx for providers that do that: trying again changes nothing) and IntegrationAuthFailed (401, 403).

Never call a provider inside transaction.atomic(): a failure would roll back its own log line and the circuit
breaker's count with the caller's changes. Claim the row instead (shipping's ShipmentDetail.claim)."""

import logging
import time
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from .models import IntegrationCall
from .redact import excerpt, scrub

logger = logging.getLogger(__name__)


class IntegrationError(Exception):
    """A call to a provider that did not succeed; `account`, `status_code` and the decoded answer (`data`) say more."""

    def __init__(self, message, *, account=None, status_code=None, data=None):
        super().__init__(message)
        self.account, self.status_code, self.data = account, status_code, data


class IntegrationUnavailable(IntegrationError):
    """Unreachable, too slow, 429 or 5xx: try again later (the tasks retry it with a growing delay)."""


class CircuitOpen(IntegrationUnavailable):
    """The account's circuit is open, or the account is disabled: no call was made (the tasks wait for it)."""


class IntegrationRejected(IntegrationError):
    """The provider answered and refused the request: trying it again unchanged changes nothing."""


class IntegrationAuthFailed(IntegrationError):
    """The provider refused the credentials or the token (401, 403)."""


def describe(data):
    """The provider's own words for a refusal, scrubbed of phone numbers and email addresses."""
    if isinstance(data, dict):
        for key in ("message", "error", "detail", "errors"):
            if data.get(key):
                return scrub(str(data[key]))[:300]
    return ""


class Client:
    """One provider's API for one account. A subclass sets base_url and may give headers() (its authentication),
    body_error() (an error the provider answers with a 2xx) and request_id() (the provider's id for the request)."""

    base_url = ""

    def __init__(self, account, transport=None, force=False):
        """`force`: call even while the circuit is open or the account disabled (staff's connection test)."""
        self.account, self.transport, self.force = account, transport, force

    def headers(self):
        return {}

    def body_error(self, response, data):
        """Why a 2xx answer is a refusal all the same, or "" (the provider's own conventions)."""
        return ""

    def request_id(self, response):
        return response.headers.get("x-request-id") or response.headers.get("x-amzn-requestid", "")

    def request(self, method, path, *, operation, json=None, params=None, timeout=None, auth=True, raw=False):
        """Call the provider: the decoded JSON answer (None when empty), or the response itself with `raw` (a file).
        `path` is relative to base_url, or a whole URL (a label's file); `timeout` in seconds replaces both
        timeouts. Raises CircuitOpen without calling while the circuit says wait."""
        if not self.force and not self.account.allows_call():
            state = self.account.get_circuit_state_display() if self.account.enabled else "disabled"
            raise CircuitOpen(f"{self.account}: no call made ({state})", account=self.account)
        url = urlsplit(path)
        logged = f"{url.netloc}{url.path}" if url.netloc else url.path
        call = IntegrationCall(account=self.account, operation=operation, method=method, path=logged[:300])
        started = time.monotonic()
        limits = httpx.Timeout(timeout) if timeout else self.timeout()
        try:
            with httpx.Client(base_url=self.base_url, timeout=limits, transport=self.transport) as http:
                response = http.request(
                    method, path, json=json, params=params, headers=self.headers() if auth else None
                )
        except httpx.HTTPError as error:  # connection refused or reset, DNS, timeouts, protocol errors
            problem = f"{type(error).__name__}: no answer"
            self._log(call, started, problem, json, None)
            self.account.record_failure(problem)
            logger.warning("%s %s failed: %s", self.account, operation, problem)
            raise IntegrationUnavailable(f"{self.account} {operation}: {problem}", account=self.account) from error
        data = None
        if not raw and response.content:
            try:
                data = response.json()
            except ValueError:
                data = None
        call.status_code, call.provider_request_id = response.status_code, self.request_id(response)[:100]
        status = response.status_code
        error_class, problem = None, ""
        if status == 429 or status >= 500:
            error_class, problem = IntegrationUnavailable, f"HTTP {status}"
        elif status in (401, 403):
            error_class, problem = IntegrationAuthFailed, f"HTTP {status}: {describe(data)}".rstrip(": ")
        elif status >= 400:
            error_class, problem = IntegrationRejected, f"HTTP {status}: {describe(data)}".rstrip(": ")
        elif refusal := self.body_error(response, data):
            error_class, problem = IntegrationRejected, f"HTTP {status}: {scrub(refusal)[:300]}"
        self._log(call, started, problem, json, response.content if raw else data)
        if error_class is None:
            self.account.record_success()
            return response if raw else data
        if error_class is IntegrationUnavailable:
            self.account.record_failure(problem)
        else:  # it answered: the provider is up, our request (or our key) is what failed
            self.account.record_success(answered_only=True)
            self.account.record_error(problem)
        logger.warning("%s %s failed: %s", self.account, operation, problem)
        raise error_class(f"{self.account} {operation}: {problem}", account=self.account, status_code=status, data=data)

    def timeout(self):
        return httpx.Timeout(settings.INTEGRATIONS_READ_TIMEOUT, connect=settings.INTEGRATIONS_CONNECT_TIMEOUT)

    def _log(self, call, started, problem, sent, received):
        call.duration_ms = int((time.monotonic() - started) * 1000)
        call.error = problem[:500]
        parts = [f"→ {excerpt(sent, 450)}" if sent else "", f"← {excerpt(received, 500)}" if received else ""]
        call.excerpt = "\n".join(part for part in parts if part)
        call.save()
