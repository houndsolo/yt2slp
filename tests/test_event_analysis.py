from itertools import combinations
import pytest

from yt2slp.event_analysis import event_counts, rates


def test_events_are_matched_once_and_tolerances_do_not_shift_predictions():
    predicted, actual = [10, 11, 15, 30], [11, 16, 28]
    assert event_counts(predicted, actual) == dict(tp=1, fp=3, fn=2)
    assert event_counts(predicted, actual, 1) == dict(tp=2, fp=2, fn=1)
    assert event_counts(predicted, actual, 2) == dict(tp=3, fp=1, fn=0)
    assert predicted == [10, 11, 15, 30]


def test_greedy_matching_has_maximum_cardinality_on_small_exhaustive_cases():
    sequences = [list(c) for n in range(4) for c in combinations(range(5), n)]
    def best(a, b, tol):
        if not a or not b: return 0
        return max(best(a[1:], b, tol), best(a, b[1:], tol),
                   1+best(a[1:], b[1:], tol) if abs(a[0]-b[0]) <= tol else 0)
    for a in sequences:
        for b in sequences:
            for tolerance in (0, 1, 2): assert event_counts(a, b, tolerance)['tp'] == best(a, b, tolerance)


def test_unknown_or_invalid_events_are_not_invented():
    assert rates(event_counts([], []))['f1'] is None
    assert rates(event_counts([1], []))['precision'] == 0
    for events in ([1, 1], [2, 1], [1.5]):
        with pytest.raises(ValueError): event_counts(events, [])
    with pytest.raises(ValueError): event_counts([], [], -1)
