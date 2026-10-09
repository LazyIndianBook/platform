"""The arithmetic of the insights jobs, on plain lists (no database), so that each piece is checked on numbers worked
out by hand (insights/tests/test_stats.py). A season's weekly series runs forward in time: index 0 is the season's
first week, the last index the week just before the exam."""

import math
from statistics import NormalDist, StatisticsError, correlation

DAMPING_WEEKS = 4  # the growth factor counts for weeks / (weeks + 4): half after four weeks of this season
DEFAULT_SPREAD = (0.6, 1.5)  # P10 and P90 as multiples of P50 while no season of errors exists to measure them by
MIN_RATIOS = 10  # weeks of errors needed before the spread is measured rather than the default
Z = NormalDist()
Z90 = Z.inv_cdf(0.9)  # 1.2816: P10 and P90 lie this many standard deviations from the median


def quantile(values, q):
    """The q-quantile (0 to 1) of the values, interpolated between the two nearest ones (numpy's default, Excel's
    PERCENTILE.INC); None without values."""
    values = sorted(values)
    if not values:
        return None
    position = q * (len(values) - 1)
    low = math.floor(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def damped_growth(this, last, weeks, damping=DAMPING_WEEKS):
    """This season to date ÷ the same weeks last season, pulled toward 1 while few weeks are in (weight
    weeks / (weeks + damping)); 1 when last season sold nothing in those weeks."""
    if last <= 0:
        return 1.0
    return 1 + (this / last - 1) * weeks / (weeks + damping)


def rolling_origin(previous, last, horizon, damping=DAMPING_WEEKS):
    """A backtest across `last` (a season's weekly copies; `previous` the season before, as long): from each origin
    (the weeks before it known, at least one) the forecast `horizon` weeks ahead, by the seasonal naive (the same week
    of `previous`) and by the seasonal naive × the damped growth known at the origin. [(actual, method, naive)]."""
    points = []
    for origin in range(1, len(last) - horizon + 1):
        growth = damped_growth(sum(last[:origin]), sum(previous[:origin]), origin, damping)
        week = origin + horizon - 1
        points.append((last[week], previous[week] * growth, previous[week]))
    return points


def wape(points, column=1):
    """Weighted absolute percentage error of the method (column 1) or the naive (column 2): the sum of absolute errors ÷
    the copies sold. None when nothing sold. (Never MAPE: it divides by weeks that sold nothing.)"""
    sold = sum(point[0] for point in points)
    return sum(abs(point[0] - point[column]) for point in points) / sold if sold else None


def mase(points):
    """The method's mean absolute error scaled by the seasonal naive's on the same weeks (the seasonal MASE: the naive's
    forecast does not move with the origin): below 1 the method beats the naive. None when the naive made no error."""
    scale = sum(abs(actual - naive) for actual, _, naive in points)
    return sum(abs(actual - method) for actual, method, _ in points) / scale if scale else None


def spread(points):
    """P10 and P90 as multiples of P50: the 10th and 90th percentiles of actual ÷ forecast over the backtest's weeks,
    widened to hold 1; the stated DEFAULT_SPREAD with fewer than MIN_RATIOS weeks to measure."""
    ratios = [actual / method for actual, method, _ in points if method > 0]
    if len(ratios) < MIN_RATIOS:
        return DEFAULT_SPREAD
    return min(quantile(ratios, 0.1), 1.0), max(quantile(ratios, 0.9), 1.0)


def critical_ratio(net_price, unit_cost, salvage):
    """The newsvendor's quantile: Cu ÷ (Cu + Co), where a copy short loses Cu = net price − print cost and a copy too
    many costs Co = print cost − salvage. 0 when a copy sells at a loss, 1 when a spare copy costs nothing."""
    under, over = float(net_price - unit_cost), float(unit_cost - salvage)
    if under <= 0:
        return 0.0
    if over <= 0:
        return 1.0
    return under / (under + over)


def quantile_between(p10, p50, p90, q):
    """The q-quantile of a demand known by its P10, P50 and P90: log-linear in the normal score from the median to the
    P90 above it and to the P10 below (a log-normal through the three points, each side its own spread)."""
    if p50 <= 0:
        return 0.0
    z = Z.inv_cdf(min(max(q, 0.001), 0.999))
    edge = p90 if z >= 0 else p10
    if edge <= 0:
        return 0.0
    return p50 * (edge / p50) ** (abs(z) / Z90)


def weeks_of_cover(supply, weekly):
    """How many of the coming weeks (their median demand, in order) the supply lasts, with the week it runs out in as a
    fraction; None when it outlasts them all."""
    for weeks, need in enumerate(weekly):
        if supply < need:
            return weeks + supply / need
        supply -= need
    return None


def point_biserial(right, scores):
    """The correlation of a 0/1 answer with a score (Pearson's r, which is the point-biserial); None when either does
    not vary."""
    try:
        return correlation(right, scores)
    except StatisticsError:
        return None


def ratio_interval(a, b):
    """A 95 % interval for the ratio of two counts a ÷ b (each taken as Poisson: the normal approximation on the log
    scale, exp(ln(a/b) ± 1.96·√(1/a + 1/b))); None when either is 0."""
    if not a or not b:
        return None
    half = Z.inv_cdf(0.975) * math.sqrt(1 / a + 1 / b)
    return math.exp(math.log(a / b) - half), math.exp(math.log(a / b) + half)
