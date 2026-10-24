import runpy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/learning'))
comparison = runpy.run_path(str(ROOT/'tools/learning/summarize_state.py'))['comparison']


def test_state_gain_does_not_override_accuracy_or_airborne_regressions():
    import json
    plan = json.loads((ROOT/'configs/state-vision-experiment-v1.json').read_text())
    base = dict(action_macro_recall=.1, action_accuracy=.4, airborne_balanced_accuracy=.7)
    tuned = dict(action_macro_recall=.14, action_accuracy=.41, airborne_balanced_accuracy=.71)
    pending = comparison({'frozen': base, 'finetuned': tuned}, plan)
    assert pending['criteria_met'] and not pending['state_pilot_passed']
    assert comparison({'frozen': base, 'finetuned': tuned}, plan, True)['state_pilot_passed']
    tuned['airborne_balanced_accuracy'] = .65
    result = comparison({'frozen': base, 'finetuned': tuned}, plan, True)
    assert not result['state_pilot_passed'] and not result['controller_improvement_established']
