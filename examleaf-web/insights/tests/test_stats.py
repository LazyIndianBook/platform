"""The arithmetic of the jobs, against numbers worked out by hand."""

import math

import pytest

from insights import stats

approx = pytest.approx


def test_quantiles_interpolate_between_the_nearest_values():
    assert stats.quantile([4, 1, 3, 2], 0.5) == 2.5  # sorted 1 2 3 4: halfway between the 2nd and the 3rd
    assert stats.quantile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == approx(9.1)  # position 0.9 × 9 = 8.1
    assert stats.quantile([7], 0.9) == 7 and stats.quantile([], 0.5) is None


def test_the_growth_factor_is_damped_toward_1_while_few_weeks_are_in():
    assert stats.damped_growth(100, 50, weeks=0) == 1.0  # nothing known yet
    assert stats.damped_growth(100, 50, weeks=4) == 1.5  # a ratio of 2, weighted 4 / (4 + 4)
    assert stats.damped_growth(100, 50, weeks=36) == approx(1.9)  # weight 36 / 40
    assert stats.damped_growth(30, 0, weeks=10) == 1.0  # last season sold nothing then: no ratio
    assert stats.damped_growth(50, 50, weeks=20) == 1.0


def test_with_a_growth_of_1_the_forecast_is_last_season_again():
    previous, last = [3, 0, 5, 8, 2], [3, 0, 5, 8, 2]  # this season as last: every growth factor is 1
    points = stats.rolling_origin(previous, last, horizon=1)
    assert [method for _, method, _ in points] == [0, 5, 8, 2] == [naive for _, _, naive in points]


def test_the_backtest_errors_of_a_hand_made_series():
    """previous = 10 0 10 10, last = 20 5 10 20, damping 4. One week ahead, from the origins after weeks 1, 2, 3:
    growth 1 + (20/10 − 1)·1/5 = 1.2, 1 + (25/10 − 1)·2/6 = 1.5, 1 + (35/20 − 1)·3/7 = 1 + 2.25/7; forecasts 0, 15 and
    10 + 22.5/7 against 5, 10, 20; the naive's 0, 10, 10."""
    previous, last = [10, 0, 10, 10], [20, 5, 10, 20]
    points = stats.rolling_origin(previous, last, horizon=1)
    assert points == [(5, 0, 0), (10, 15, 10), (20, approx(10 + 22.5 / 7), 10)]
    method_errors = 5 + 5 + (20 - (10 + 22.5 / 7))  # 117.5 / 7
    assert stats.wape(points) == approx(method_errors / 35) == approx(117.5 / 245)
    assert stats.wape(points, column=2) == approx(15 / 35)
    assert stats.mase(points) == approx(method_errors / 15) == approx(117.5 / 105)  # above 1: the naive wins
    # two weeks ahead: from the origins after weeks 1 and 2, the forecasts of weeks 3 and 4
    points = stats.rolling_origin(previous, last, horizon=2)
    assert points == [(10, 12, 10), (20, 15, 10)]
    assert (stats.wape(points), stats.mase(points)) == (approx(7 / 30), approx(7 / 10))  # below 1: it wins


def test_the_spread_comes_from_the_errors_once_there_are_enough_weeks():
    assert stats.spread([(1, 1, 1)] * 9) == stats.DEFAULT_SPREAD  # nine weeks: the stated default
    ratios = [0.5, 0.8, 0.9, 1.0, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]  # actual ÷ forecast, ten weeks
    low, high = stats.spread([(ratio * 10, 10, 10) for ratio in ratios])
    assert (low, high) == (approx(0.5 + 0.9 * 0.3), approx(1.5 + 0.1 * 0.5))  # positions 0.9 and 8.1
    assert stats.spread([(20, 10, 10)] * 10) == (1.0, 2.0)  # the range always holds the median


def test_the_newsvendor_prints_the_p71_in_the_research_example():
    """Net ₹195, print cost ₹60, salvage ₹5: Cu = 135, Co = 55, ratio 135/190 = 0.71."""
    ratio = stats.critical_ratio(195, 60, 5)
    assert ratio == 135 / 190 and f"P{round(ratio * 100)}" == "P71"
    assert stats.critical_ratio(50, 60, 5) == 0.0  # sold at a loss: print nothing extra
    assert stats.critical_ratio(195, 60, 60) == 1.0  # a spare copy costs nothing


def test_a_quantile_between_p10_p50_and_p90_is_log_normal_on_each_side():
    assert stats.quantile_between(60, 100, 150, 0.9) == approx(150)
    assert stats.quantile_between(60, 100, 150, 0.1) == approx(60)
    assert stats.quantile_between(60, 100, 150, 0.5) == approx(100)
    z = 0.554923  # the normal score of 135/190 = 0.7105 (Φ(0.55) = 0.7088, Φ(0.56) = 0.7123)
    assert stats.quantile_between(60, 100, 150, 135 / 190) == approx(100 * 1.5 ** (z / 1.281552), rel=1e-5)
    assert stats.quantile_between(0, 0, 0, 0.71) == 0


def test_weeks_of_cover_walk_through_the_coming_weeks():
    assert stats.weeks_of_cover(25, [10, 10, 10]) == 2.5  # two weeks, then half of the third
    assert stats.weeks_of_cover(0, [10, 10]) == 0
    assert stats.weeks_of_cover(40, [10, 10, 10]) is None  # it outlasts the season


def test_the_point_biserial_is_the_textbook_formula():
    right = [1, 1, 1, 0, 0, 1, 0, 1]
    scores = [0.9, 0.7, 0.8, 0.4, 0.6, 0.5, 0.3, 1.0]
    m1 = (0.9 + 0.7 + 0.8 + 0.5 + 1.0) / 5
    m0 = (0.4 + 0.6 + 0.3) / 3
    mean = sum(scores) / 8
    sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / 8)  # the population standard deviation
    assert stats.point_biserial(right, scores) == approx((m1 - m0) / sd * math.sqrt(5 / 8 * 3 / 8))
    assert stats.point_biserial([1, 1, 1], [0.2, 0.4, 0.6]) is None  # an item everyone got right says nothing


def test_the_interval_of_a_ratio_of_counts():
    low, high = stats.ratio_interval(120, 100)
    half = 1.959964 * math.sqrt(1 / 120 + 1 / 100)
    assert (low, high) == (approx(1.2 * math.exp(-half), rel=1e-6), approx(1.2 * math.exp(half), rel=1e-6))
    assert stats.ratio_interval(0, 100) is None and stats.ratio_interval(5, 0) is None
