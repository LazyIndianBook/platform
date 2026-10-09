"""The legal clocks in calendar time (plan 9.2's exit criterion): a month across month ends and in a leap year, 48 hours
across India's midnight, the earliest clock that applies, the SPDI Rules' month until the DPDP Rules and their 90
days after, the NCH's 30 days, the IT Rules' only while they are switched on. Pure functions: no database."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from support.clocks import ACK, RESOLVE, add_month, clocks, earliest, warn_at

INDIA = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")
DPDP = date(2027, 5, 13)


def ist(*parts):
    return datetime(*parts, tzinfo=INDIA)


def due(found, name):
    return next(clock.due for clock in found if clock.name == name)


def test_a_month_runs_to_the_same_day_or_the_last_of_a_shorter_month_at_the_same_time():
    assert add_month(ist(2027, 1, 31, 14, 0)) == ist(2027, 2, 28, 14, 0)  # the exit criterion's own case
    assert add_month(ist(2027, 3, 31, 9, 30)) == ist(2027, 4, 30, 9, 30)
    assert add_month(ist(2028, 1, 31, 14, 0)) == ist(2028, 2, 29, 14, 0)  # a leap year
    assert add_month(ist(2028, 1, 29, 8, 0)) == ist(2028, 2, 29, 8, 0)
    assert add_month(ist(2026, 12, 15, 23, 59)) == ist(2027, 1, 15, 23, 59)  # across the year
    assert add_month(ist(2027, 2, 28, 10, 0)) == ist(2027, 3, 28, 10, 0)  # not to the month's end


def test_the_month_is_india_s_even_when_the_moment_comes_in_utc():
    """1 March 02:00 in India is still 28 February in UTC: its month ends 1 April in India, not 28 March."""
    received = ist(2027, 3, 1, 2, 0).astimezone(UTC)
    assert received.day == 28
    assert add_month(received) == ist(2027, 4, 1, 2, 0)
    assert add_month(ist(2027, 1, 31, 23, 30).astimezone(UTC)) == ist(2027, 2, 28, 23, 30)


def test_48_hours_cross_india_s_midnight_and_month_ends_in_calendar_time():
    found = clocks(ist(2027, 1, 30, 23, 0), category="order", source="form", dpdp_from=DPDP)
    assert due(found, "ack") == ist(2027, 2, 1, 23, 0)
    assert earliest(found, ACK) == ist(2027, 2, 1, 23, 0)


def test_a_complaint_is_acknowledged_in_48_hours_and_redressed_in_a_month():
    found = clocks(ist(2027, 1, 31, 14, 0), category="order", source="email", dpdp_from=DPDP)
    assert [clock.name for clock in found] == ["ack", "redress"]
    assert earliest(found, RESOLVE) == ist(2027, 2, 28, 14, 0)
    unsorted = clocks(ist(2027, 1, 31, 14, 0), category="", source="form", dpdp_from=DPDP)  # not sorted yet
    assert earliest(unsorted, RESOLVE) == ist(2027, 2, 28, 14, 0)


def test_the_earliest_of_the_nch_s_30_days_and_the_month_applies():
    """A month is 28 to 31 days: after 1 February the month comes first, after 1 March NCH's 30 days do."""
    february = clocks(ist(2027, 2, 1, 10, 0), category="order", source="nch", dpdp_from=DPDP)
    assert due(february, "redress") == ist(2027, 3, 1, 10, 0)
    assert due(february, "nch") == ist(2027, 3, 3, 10, 0)
    assert earliest(february, RESOLVE) == ist(2027, 3, 1, 10, 0)
    march = clocks(ist(2027, 3, 1, 10, 0), category="order", source="nch", dpdp_from=DPDP)
    assert earliest(march, RESOLVE) == due(march, "nch") == ist(2027, 3, 31, 10, 0)


def test_a_privacy_request_has_the_spdi_month_before_the_dpdp_rules_and_90_days_from_them():
    before = clocks(ist(2027, 5, 12, 23, 59), category="privacy_request", source="form", dpdp_from=DPDP)
    assert [clock.name for clock in before] == ["ack", "dpdp"]  # no E-Commerce month: not a consumer complaint
    assert due(before, "dpdp") == ist(2027, 6, 12, 23, 59)  # both computed, the month is earlier
    assert "SPDI" in next(clock.rule for clock in before if clock.name == "dpdp")
    after = clocks(ist(2027, 5, 13, 0, 0), category="privacy_request", source="form", dpdp_from=DPDP)
    assert due(after, "dpdp") == ist(2027, 5, 13, 0, 0) + timedelta(days=90) == ist(2027, 8, 11, 0, 0)
    midnight_utc = ist(2027, 5, 13, 1, 0).astimezone(UTC)  # still 12 May in UTC: India's date decides
    assert due(clocks(midnight_utc, category="privacy_request", source="form", dpdp_from=DPDP), "dpdp") == ist(
        2027, 8, 11, 1, 0
    )


def test_the_it_rules_apply_to_grievances_only_while_switched_on():
    received = ist(2027, 2, 10, 12, 0)
    off = clocks(received, category="grievance", source="form", dpdp_from=DPDP, intermediary=False)
    assert {clock.name for clock in off} == {"ack", "redress"}
    on = clocks(received, category="grievance", source="form", dpdp_from=DPDP, intermediary=True)
    assert earliest(on, ACK) == ist(2027, 2, 11, 12, 0)  # 24 hours before 48
    assert earliest(on, RESOLVE) == ist(2027, 2, 25, 12, 0)  # 15 days before the month
    order = clocks(received, category="order", source="form", dpdp_from=DPDP, intermediary=True)
    assert {clock.name for clock in order} == {"ack", "redress"}


def test_the_inbox_is_told_once_three_quarters_of_a_clock_has_gone():
    received = ist(2027, 1, 1, 0, 0)
    assert warn_at(received, received + timedelta(hours=48)) == ist(2027, 1, 2, 12, 0)
