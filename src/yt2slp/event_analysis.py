"""One-to-one timing diagnostics; never align or change a predicted sequence."""


def event_counts(predicted, actual, tolerance=0):
    if type(tolerance) is not int or tolerance < 0: raise ValueError('nonnegative integer tolerance required')
    for events in (predicted, actual):
        if any(type(x) is not int for x in events) or any(a >= b for a, b in zip(events, events[1:])):
            raise ValueError('sorted unique integer events required')
    left = right = matched = 0
    while left < len(predicted) and right < len(actual):
        difference = predicted[left]-actual[right]
        if difference < -tolerance: left += 1
        elif difference > tolerance: right += 1
        else: matched += 1; left += 1; right += 1
    return {'tp': matched, 'fp': len(predicted)-matched, 'fn': len(actual)-matched}


def rates(counts):
    tp, fp, fn = (counts[key] for key in ('tp', 'fp', 'fn'))
    return {**counts, 'precision': tp/(tp+fp) if tp+fp else None,
        'recall': tp/(tp+fn) if tp+fn else None,
        'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
