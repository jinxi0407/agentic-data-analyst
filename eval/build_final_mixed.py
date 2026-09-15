"""Isolated benchmark authoring. No Gate or historical-result imports/inputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import BaseModel, ConfigDict
from app.tools.database import fetch_all
from app.tools.qwen import generate_text
from eval.scoring import digest, fingerprint, write_json
from eval.strong_baseline import BUSINESS_CONTEXT, schema_context
from eval.strong_baseline_v2 import STATIC_SCHEMA_METADATA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eval/final_mixed_authoring'
PROTOCOL = ROOT / 'eval/mixed_clarification_protocol.json'
LOCK = ROOT / 'eval/conservative_gate_final_freeze.json'


class Item(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str
    category: Literal['filtering','aggregation','top_k','time','product','customer','refund','join','paraphrase']
    difficulty: Literal['easy','medium','hard']
    kind: Literal['clear','time','metric','entity_filter']
    intended_meaning: str
    simulated_answer: str
    answer_slot: Literal['none','time','metric','entity','filter']
    ambiguity_explanation: str
    semantic_signature: str
    reference_sql: str
    ordered: bool


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    cases: list[Item]


INSTRUCTION = """Author a synthetic Chinese daily-business analytics evaluation, not an Agent.
Return only JSON matching the supplied schema. You have ONLY the evaluation protocol,
existing database/business contract and your previously authored intent signatures.
Never assume knowledge of a target Gate, its prompt, performance, or failed questions.
Create the exact requested number and kind. Use natural operational/sales language.
Each query must specify the requested output columns; monetary results round 2 decimals,
rates round 4. Use ordinary SELECT/CTE read-only MySQL 8, at most 5 output columns and 100 rows.
Do not add filters, output columns, metric definitions or time bounds absent from the question
or supplied contract. Respect explicit all-status requests and independent fact grain.
Different cities/numbers alone do not create distinct problems: vary the actual business
intent, projection, aggregation grain and meaningful predicates. Avoid repeated SQL templates.
Cover the requested business categories, with predominantly easy/medium practical questions.
Do not manufacture riddles, extreme ambiguity or arbitrarily complicated SQL.
Clear: every necessary choice uniquely resolved by question+contract+schema, answer empty,
answer_slot none. Unqualified totals can cover all history. intended_meaning restates the query.
Ambiguous: exactly ONE material choice missing, two reasonable interpretations survive the
contract. Every other necessary choice explicit. Freeze one intended value and a short answer
that supplies ONLY that value. reference_sql answers that intended meaning, not a guessed
default. Never include a complete resolved query, SQL or result in simulated_answer.
An ambiguous metric cannot be an already-defined metric; an ambiguous time cannot be a
fully specified relative duration/calendar period. Entity/filter ambiguity must not be an
unknown literal which legitimately returns zero rows. No unsupported database concepts.
Use only supplied metadata literals. Dates are explicit with fixed reference 2026-09-12.
Retain legitimate empty results; do not select questions based on result size or accuracy.
"""


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    assert LOCK.exists(), 'No benchmark creation before Gate freeze'
    frozen = read(LOCK)
    commit = subprocess.check_output(['/usr/bin/git','rev-parse','HEAD'], cwd=ROOT,
        env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'}).decode().strip()
    assert commit == frozen['commit']
    assert fingerprint(fetch_all) == frozen['database']
    OUT.mkdir(exist_ok=True)
    packet = {'protocol': read(PROTOCOL), 'business_contract': BUSINESS_CONTEXT,
        'schema': schema_context(), 'schema_metadata': STATIC_SCHEMA_METADATA,
        'cities': fetch_all('SELECT DISTINCT city,province FROM users ORDER BY city,province'),
        'brands_categories': fetch_all('SELECT DISTINCT brand,category FROM products ORDER BY brand,category'),
        'refund_reasons': fetch_all('SELECT DISTINCT refund_reason FROM refunds ORDER BY refund_reason')}
    inputs = OUT / 'allowed_inputs.json'
    if inputs.exists():
        assert read(inputs) == packet
    else:
        write_json(inputs, packet)
    kinds = ['clear'] * 14 + ['time'] * 2 + ['metric'] * 2 + ['entity_filter'] * 2
    all_cases = []
    for i, kind in enumerate(kinds):
        result_file = OUT / f'batch_{i:02d}.json'
        if result_file.exists():
            items = [Item.model_validate(x) for x in read(result_file)]
        else:
            request = {'allowed_inputs':packet, 'kind':kind, 'count':10,
                       'previous_signatures':[x['semantic_signature'] for x in all_cases]}
            messages = [{'role':'system','content':INSTRUCTION},
                        {'role':'user','content':json.dumps(request,ensure_ascii=False)}]
            request_file = OUT / f'batch_{i:02d}_request.json'
            assert not request_file.exists(), 'Interrupted authoring request: inspect, do not duplicate'
            write_json(request_file, messages)
            raw = generate_text(messages, temperature=.7, response_format={
                'type':'json_schema','json_schema':{'name':'business_benchmark','strict':True,
                                                  'schema':Batch.model_json_schema()}})
            write_json(OUT / f'batch_{i:02d}_raw.json', {'raw':raw})
            items = Batch.model_validate_json(raw).cases
            assert len(items) == 10 and all(x.kind == kind for x in items)
            for x in items:
                assert (x.answer_slot == 'none' and not x.simulated_answer) if kind == 'clear' else (
                    x.answer_slot in ({'entity','filter'} if kind == 'entity_filter' else {kind})
                    and bool(x.simulated_answer.strip()))
            write_json(result_file, [x.model_dump() for x in items])
        for item in items:
            all_cases.append({'id':f'final_mixed_{len(all_cases)+1:03d}',
                              'reference_date':'2026-09-12',**item.model_dump()})
        print(f'Independently authored {len(all_cases)}/200; no candidate calls',flush=True)
    draft = OUT / 'draft_cases.json'
    assert not draft.exists()
    write_json(draft,all_cases)
    write_json(OUT / 'provenance.json', {'code_commit':commit,'generator_sha256':sha(Path(__file__)),
        'allowed_inputs_digest':digest(packet),'draft_sha256':sha(draft),
        'generation_model':'qwen-plus','gate_or_failure_inputs':False,
        'candidate_runs':0,'status':'DRAFT: reference and novelty review still required'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['build'])
    parser.parse_args()
    build()
