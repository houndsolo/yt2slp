"""Evaluate a paired state pilot against its fixed development rollout gates."""
import argparse
from runtime_files import ROOT, atomic_json, digest, read_json


def comparison(metrics, plan, training_completed=False):
    frozen, tuned = metrics['frozen'], metrics['finetuned']
    gains = {name: tuned[name]-frozen[name] for name in ('action_macro_recall', 'action_accuracy', 'airborne_balanced_accuracy')}
    checks = {'action_macro_gain': gains['action_macro_recall'] >= plan['minimum_action_macro_gain'],
        'action_accuracy': gains['action_accuracy'] >= -plan['maximum_action_accuracy_drop'],
        'airborne_balanced_accuracy': gains['airborne_balanced_accuracy'] >= -plan['maximum_airborne_balanced_accuracy_drop']}
    return {'gains': gains, 'checks': checks, 'criteria_met': all(checks.values()),
        'training_completed': training_completed, 'state_pilot_passed': training_completed and all(checks.values()),
        'controller_improvement_established': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--config', required=True)
    parser.add_argument('--plan', default='configs/state-vision-experiment-v1.json'); args = parser.parse_args()
    config = read_json(ROOT/args.config); plan = read_json(ROOT/args.plan); run = ROOT/config['run_directory']
    if digest(run/'experiment-plan.json') != digest(ROOT/args.plan):
        raise ValueError('experiment gates changed after launch; retain the original plan')
    best = read_json(run/'best.json')
    if not best: raise ValueError('no validation checkpoint yet')
    import json
    record = next(json.loads(line) for line in (run/'metrics.ndjson').read_text().splitlines() if json.loads(line)['step'] == best['step'])
    if digest(run/best['file']) != best['sha256']: raise ValueError('selected model checksum changed')
    complete = read_json(run/'status.json', {}).get('state') == 'completed'
    compared = comparison(record['validation'], plan, complete)
    result = {'kind': 'matched-state-vision-summary', 'checkpoint': best, 'plan_sha256': digest(ROOT/args.plan),
        'metrics': record['validation'], **compared, 'test_matches_opened': 0,
        'policy': 'development pilot; paired same-update comparison; no controls/reconstructed gameplay or unseen-test claim'}
    atomic_json(run/'experiment-result.json', result); print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
