"""Regression I/O adapter for the disclosed Mixed dataset; no new scoring rules."""

import argparse
from collections import Counter
from datetime import date
import fcntl
import json
import time
from unittest.mock import patch

from eval import run_final_mixed as original
from eval.scoring import fingerprint, write_json

ROOT = original.ROOT
SHARED = original.shared


def artifact(suffix):
    return ROOT / ('eval/final_mixed_regression_' + suffix)


def validate():
    snapshot = SHARED.read(artifact('freeze.json'))
    for name, digest in snapshot['hashes'].items():
        assert SHARED.sha(ROOT / name) == digest, f'Frozen artifact changed: {name}'
    assert SHARED.sha(ROOT / 'eval/final_mixed_freeze.json') == snapshot['original_manifest_sha256']
    assert fingerprint(original.fetch_all) == snapshot['database']
    config = SHARED.public_config()
    for key in ('chat_model', 'embedding_model', 'sql_temperature', 'gate_temperature',
                'execution_retry_limit', 'gate_format_retry_limit', 'sql_max_rows', 'sdk_version'):
        assert config[key] == snapshot['model_config'][key], key
    assert snapshot['workers_per_mode'] == {'off': 1, 'on': 1}
    cases = SHARED.read(original.DATA)
    assert len(cases) == 200 and Counter(c['kind'] for c in cases) == snapshot['data_distribution']
    for name in snapshot['hashes']:
        if name.startswith(('app/', 'ui/', 'scripts/')):
            tracked = SHARED.git('show', snapshot['code_commit'] + ':' + name)
            assert tracked.rstrip() == (ROOT / name).read_text().rstrip(), name
    return snapshot, cases


def redirected_write(path, value):
    assert path.parent == ROOT / 'eval' and path.name.startswith('final_mixed_')
    write_json(artifact(path.name.removeprefix('final_mixed_')), value)


def first():
    snapshot, cases = validate()
    rows = original.records()
    assert not any(r.get('failures') for r in rows.values()), 'Previous infrastructure halt'
    identity = {'code_commit': snapshot['code_commit'],
                'manifest_sha256': SHARED.sha(artifact('freeze.json')),
                'runner_sha256': SHARED.sha(ROOT / 'eval/run_final_mixed_regression.py'),
                'workers': {'off': 1, 'on': 1}, 'evaluation': 'disclosed benchmark regression'}
    path = artifact('run_freeze.json')
    if path.exists():
        assert SHARED.read(path)['identity'] == identity
    else:
        assert not rows
        write_json(path, {'identity': identity, 'created_unix': time.time()})
    original.entity_context()
    reference = date.fromisoformat(snapshot['reference_date'])
    for i, case in enumerate(cases):
        for mode in (('off', 'on') if i % 2 == 0 else ('on', 'off')):
            original.execute(rows, case['id'], mode,
                             lambda c=case, m=mode: original.candidate(c['question'], reference, m))
        print(f'Paired first turns {i + 1}/200', flush=True)
    validate()
    packets = [original.answer_packet(c, rows[(c['id'], 'on')]['payload']) for c in cases
               if rows[(c['id'], 'on')]['payload']['status'] == 'needs_clarification']
    write_json(artifact('reply_packet.json'), packets)
    print(f'Answer eligibility review required: {len(packets)}', flush=True)


def followup():
    validate()
    rows = original.records()
    assert not any(r.get('failures') for r in rows.values()), 'Previous infrastructure halt'
    packets = SHARED.read(original.PACKET)
    reviews = {r['id']: r for r in SHARED.read(original.REVIEWS)}
    assert len(reviews) == len(packets) and set(reviews) == {p['id'] for p in packets}
    hashes = {'packet': SHARED.sha(original.PACKET), 'review': SHARED.sha(original.REVIEWS)}
    path = artifact('reply_freeze.json')
    if path.exists():
        assert SHARED.read(path) == hashes
    else:
        write_json(path, hashes)
    for i, packet in enumerate(packets):
        answer = original.checked_answer(reviews[packet['id']], packet)
        if answer is None:
            key = (packet['id'], 'followup')
            if key not in rows:
                event = {'id': packet['id'], 'stage': 'followup', 'state': 'complete',
                         'payload': {'status': 'simulated_answer_unavailable', 'result': []},
                         'usage': [], 'failures': [], 'elapsed_s': 0}
                original.append(event)
                rows[key] = event
        else:
            context = rows[(packet['id'], 'on')]['payload']['clarification_context']
            original.execute(rows, packet['id'], 'followup',
                             lambda p=packet, c=context, a=answer:
                             original.followup_candidate(p['original_question'], c, a))
        print(f'Single-slot follow-ups {i + 1}/{len(packets)}', flush=True)
    validate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['validate', 'first', 'followup', 'summarize'])
    args = parser.parse_args()
    with (ROOT / '.run/final_mixed_regression.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.multiple(original, EVENTS=artifact('events.jsonl'),
                            PACKET=artifact('reply_packet.json'), REVIEWS=artifact('reply_review.json'),
                            validate=validate, write_json=redirected_write):
            {'validate': validate, 'first': first, 'followup': followup,
             'summarize': original.summarize}[args.phase]()


if __name__ == '__main__':
    main()
