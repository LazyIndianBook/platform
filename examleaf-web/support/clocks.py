"""The legal clocks of a ticket (plan 5.14; research lms 4.2, rbac 4.6, gst 6): what each rule allows from the moment
a complaint is received, in calendar time in India, never paused (a ticket waiting on its customer keeps running), and
which falls due first. Pure functions: support.models.Ticket.refresh_clocks stores what they give.

| Clock | Rule | Applies to | Due |
|---|---|---|---|
| ack | E-Commerce Rules 4(4) | every ticket | 48 hours |
| redress | E-Commerce Rules 4(5) | every complaint (not a privacy request) | one calendar month |
| nch | the National Consumer Helpline's convergence programme | a complaint NCH forwarded | 30 days |
| dpdp | SPDI Rules 5(9), then DPDP Rules 14(3) | a privacy request | a month before the DPDP Rules, 90 days from them |
| it_ack, it_resolve | IT Rules 3(2) | a grievance, only with SUPPORT_INTERMEDIARY_RULES on | 24 hours, 15 days |

An acknowledgement clock stops at the acknowledgement; the others at the resolution (a reopened ticket's run on from
where they were: their due times never move)."""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INDIA = ZoneInfo("Asia/Kolkata")
ACK, RESOLVE = "ack", "resolve"
PRIVACY, GRIEVANCE, NCH = "privacy_request", "grievance", "nch"  # Ticket.Category and Ticket.Source values
WARN_AT = 0.75  # the inbox hears of a running clock once three quarters of its time has gone


@dataclass(frozen=True)
class Clock:
    name: str
    kind: str  # ACK or RESOLVE
    due: datetime
    rule: str


def add_month(moment: datetime) -> datetime:
    """The same time on the same day one calendar month later in India, or on the last day of a shorter month: 31
    January 14:00 is due 28 February 14:00 (29 February in a leap year), 31 March is due 30 April, 15 December is due
    15 January. India keeps one offset all year, so the time of day never moves."""
    local = moment.astimezone(INDIA)
    year, month = local.year + local.month // 12, local.month % 12 + 1
    return local.replace(year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1]))


def clocks(received_at, *, category, source, dpdp_from, intermediary=False):
    """Every clock that applies to a ticket of this category ("" while not sorted yet: a complaint) and source received
    at that moment (a datetime with its zone), the earliest first. `dpdp_from` is the day the DPDP Rules' rights apply
    (STAFF_DPDP_RULES_FROM); `intermediary`, whether the IT Rules' grievance clocks do (SUPPORT_INTERMEDIARY_RULES)."""
    found = [Clock("ack", ACK, received_at + timedelta(hours=48), "E-Commerce Rules 4(4): acknowledge in 48 hours")]
    if category != PRIVACY:
        found.append(Clock("redress", RESOLVE, add_month(received_at), "E-Commerce Rules 4(5): redress within a month"))
    if source == NCH:
        found.append(Clock("nch", RESOLVE, received_at + timedelta(days=30), "National Consumer Helpline: 30 days"))
    if category == PRIVACY:
        ninety = received_at + timedelta(days=90)
        if received_at.astimezone(INDIA).date() < dpdp_from:  # both computed, the earliest applies: the SPDI month
            found.append(Clock("dpdp", RESOLVE, min(add_month(received_at), ninety), "SPDI Rules 5(9): one month"))
        else:
            found.append(Clock("dpdp", RESOLVE, ninety, "DPDP Rules 14(3): answer within 90 days"))
    if intermediary and category == GRIEVANCE:
        found.append(Clock("it_ack", ACK, received_at + timedelta(hours=24), "IT Rules 3(2): acknowledge in 24 hours"))
        found.append(
            Clock("it_resolve", RESOLVE, received_at + timedelta(days=15), "IT Rules 3(2): resolve in 15 days")
        )
    return sorted(found, key=lambda clock: clock.due)


def earliest(found, kind):
    """The earliest due time of the clocks of one kind (ACK or RESOLVE), or None."""
    return min((clock.due for clock in found if clock.kind == kind), default=None)


def warn_at(start, due):
    """When three quarters of a clock's time has gone (WARN_AT)."""
    return start + (due - start) * WARN_AT
