"""Our parcel statuses: every Shiprocket shipment code of research 3.6 maps, an unknown one changes nothing, and a
status only moves forward (the return branch its own sequence)."""

import pytest

from shipping.status import FROM_SHIPROCKET, Status, from_shiprocket, moves_forward

S = Status
RESEARCH_TABLE = {  # research-integrations.md 3.6, row by row
    S.BOOKED: [1, 2, 3, 4, 5, 15, 19, 27, 52],
    S.PICKUP_PROBLEM: [13, 20],
    S.IN_TRANSIT: [6, 18, 22, 38, 39, 42, 48, 51],
    S.OUT_FOR_DELIVERY: [17],
    S.DELIVERED: [7, 26],
    S.DELIVERY_FAILED: [21, 77],
    S.RETURNING: [9, 40, 41, 46, 75],
    S.RETURNED: [10, 14, 78],
    S.LOST_OR_DAMAGED: [12, 24, 25, 44, 76],
    S.CANCELLED: [8, 16, 45],
    S.PARTIAL: [23],
}


@pytest.mark.parametrize("status,codes", RESEARCH_TABLE.items())
def test_every_code_of_the_research_maps(status, codes):
    for code in codes:
        assert from_shiprocket(code) == status and from_shiprocket(str(code)) == status


def test_the_table_has_nothing_else_and_unknown_codes_map_to_nothing():
    assert len(FROM_SHIPROCKET) == sum(map(len, RESEARCH_TABLE.values()))
    for code in [11, 43, 47, 99, 0, "NA", "", None, "x"]:  # pending, self fulfilled, QC failed, unknown
        assert from_shiprocket(code) is None
    assert not moves_forward(S.IN_TRANSIT, None)


FORWARD = [
    (None, S.BOOKED),
    (S.BOOKED, S.PICKUP_PROBLEM),
    (S.PICKUP_PROBLEM, S.BOOKED),  # pickup rescheduled
    (S.BOOKED, S.IN_TRANSIT),
    (S.BOOKED, S.CANCELLED),
    (S.PICKUP_PROBLEM, S.CANCELLED),
    (S.IN_TRANSIT, S.OUT_FOR_DELIVERY),
    (S.OUT_FOR_DELIVERY, S.DELIVERY_FAILED),
    (S.DELIVERY_FAILED, S.OUT_FOR_DELIVERY),  # another attempt
    (S.DELIVERY_FAILED, S.DELIVERED),
    (S.IN_TRANSIT, S.DELIVERED),  # scans missed
    (S.PARTIAL, S.DELIVERED),
    (S.IN_TRANSIT, S.RETURNING),
    (S.DELIVERY_FAILED, S.RETURNING),
    (S.RETURNING, S.RETURNED),
    (S.IN_TRANSIT, S.RETURNED),  # the return's own scans missed
    (S.RETURNING, S.LOST_OR_DAMAGED),
    (S.IN_TRANSIT, S.LOST_OR_DAMAGED),
]
BACKWARD = [
    (S.IN_TRANSIT, S.BOOKED),
    (S.OUT_FOR_DELIVERY, S.IN_TRANSIT),
    (S.DELIVERY_FAILED, S.IN_TRANSIT),  # back at the hub after an attempt: still "failed" until the next one
    (S.IN_TRANSIT, S.CANCELLED),  # picked up: nothing cancels
    (S.RETURNING, S.IN_TRANSIT),  # the return branch is its own sequence
    (S.RETURNING, S.DELIVERED),
    (S.RETURNED, S.RETURNING),
    (S.DELIVERED, S.RETURNING),  # final
    (S.DELIVERED, S.IN_TRANSIT),
    (S.CANCELLED, S.BOOKED),
    (S.LOST_OR_DAMAGED, S.DELIVERED),
    (S.IN_TRANSIT, S.IN_TRANSIT),
]


@pytest.mark.parametrize("current,new", FORWARD)
def test_forward(current, new):
    assert moves_forward(current, new)


@pytest.mark.parametrize("current,new", BACKWARD)
def test_never_back(current, new):
    assert not moves_forward(current, new)
