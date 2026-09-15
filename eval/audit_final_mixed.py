"""Local-only draft audit: no model imports, network review, Gate or failure inputs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import sqlglot
from sqlglot import exp

from app.tools.database import connection, _json_safe_row
from eval.scoring import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'eval/final_mixed_authoring_revision_1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_result(sql):
    parsed = sqlglot.parse(sql,read='mysql')
    assert len(parsed)==1 and isinstance(parsed[0],exp.Query), 'Single read-only query required'
    assert not any(parsed[0].find_all(exp.Into,exp.Lock,exp.DML,exp.DDL)), 'Unsafe reference SQL'
    ctes={c.alias for c in parsed[0].find_all(exp.CTE)}
    tables={'users','products','orders','order_items','refunds'}
    assert all(not t.db and not t.catalog and t.name in tables|ctes
               for t in parsed[0].find_all(exp.Table)), 'Reference may use only current demo tables/CTEs'
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET SESSION MAX_EXECUTION_TIME=10000')
            cur.execute('START TRANSACTION READ ONLY')
            cur.execute(sql)
            rows = cur.fetchmany(101)
    assert len(rows)<=100, 'Reference output exceeds the protocol cap'
    assert not rows or len(rows[0])<=5, 'Reference output exceeds five columns'
    return [_json_safe_row(row) for row in rows]


def sql_template(sql):
    tree = sqlglot.parse_one(sql,read='mysql')
    # Preserve logical operations and grain; mask aliases and literals for duplicate screening.
    aliases = {}
    for table in tree.find_all(exp.Table):
        aliases[table.alias_or_name] = table.name.lower()
        table.set('alias',None)
    for column in tree.find_all(exp.Column):
        if column.table in aliases:
            column.set('table',exp.to_identifier(aliases[column.table]))
    for alias in list(tree.find_all(exp.Alias)):
        name = alias.alias
        expression = alias.this.copy()
        for column in list(tree.find_all(exp.Column)):
            if not column.table and column.name == name:
                column.replace(expression.copy())
        alias.replace(expression)
    for literal in list(tree.find_all(exp.Literal)):
        literal.replace(exp.Literal.string('VALUE') if literal.is_string else exp.Literal.number(0))
    return tree.sql(dialect='mysql',normalize=True)


def history():
    # Frozen question/SQL datasets only, never model outputs or failure logs.
    names = ['eval/final_release_holdout_300.json','eval/scoped_clarification_cases.json',
             'eval/clarification_holdout.json','eval/clarification_dev.json']
    rows = []
    sources = {}
    for name in names:
        sources[name] = sha(ROOT/name)
        value = read(ROOT/name)
        if isinstance(value,dict):
            value = value.get('cases',[])
        for x in value:
            if isinstance(x,dict) and x.get('question') and x.get('reference_sql'):
                rows.append({'source':name,'id':x['id'],'question':x['question'],
                             'reference_sql':x['reference_sql']})
    historical = [
        'agent-v4-generalization-release:eval/final_cases.json',
        'agent-v4-generalization-release:eval/final_blind_v4_cases.json',
        'agent-v3-generalization:eval/holdout_cases.json',
        'agent-v3-generalization:eval/final_blind_cases.json',
    ]
    for ref in historical:
        raw = subprocess.check_output(['/usr/bin/git','show',ref],cwd=ROOT)
        sources[ref] = hashlib.sha256(raw).hexdigest()
        value = json.loads(raw)
        if isinstance(value,dict):
            value = value.get('cases',[])
        for x in value:
            if isinstance(x,dict) and x.get('question') and x.get('reference_sql'):
                rows.append({'source':ref,'id':x['id'],'question':x['question'],
                             'reference_sql':x['reference_sql']})
    return rows,sources


def audit(source='reviewed_cases.json',output='audit'):
    cases = read(OUT/source)
    assert len(cases)==200 and len({x['id'] for x in cases})==200
    assert Counter(x['kind'] for x in cases)=={'clear':140,'time':20,'metric':20,'entity_filter':20}
    folder = OUT/output
    folder.mkdir(exist_ok=True)
    assert not (folder/'reference_execution.json').exists(), 'Preserve prior reference audit'
    past,sources = history()
    templates = {}
    for x in past:
        try:
            key = sql_template(x['reference_sql'])
        except (ValueError,sqlglot.errors.ParseError):
            continue
        templates.setdefault(key,[]).append({'source':x['source'],'id':x['id']})
    own = {}
    duplicates = []
    references = []
    for c in cases:
        try:
            template = sql_template(c['reference_sql'])
            matches = templates.get(template,[]) + own.get(template,[])
            if matches:
                duplicates.append({'id':c['id'],'matches':matches,'kind':'literal-masked SQL template'})
            own.setdefault(template,[]).append({'source':'current_draft','id':c['id']})
            result = reference_result(c['reference_sql'])
            references.append({'id':c['id'],'ok':True,'ground_truth_result':result})
        except Exception as exc:
            references.append({'id':c['id'],'ok':False,'error_type':type(exc).__name__,
                               'reason':str(exc)[:1500]})
    write_json(folder/'reference_execution.json',references)
    write_json(folder/'novelty.json',{'draft_sha256':sha(OUT/source),
        'sources':sources,'historical_questions_checked':len(past),
        'duplicates':duplicates,'semantic_review_pending':True,
        'limitation':'Alias/literal-masked SQL equivalence screens duplicates but cannot prove semantic novelty.'})
    write_json(folder/'summary.json',{'candidate_calls':0,
        'reference_errors':sum(not r['ok'] for r in references),'template_matches':len(duplicates),
        'status':'LOCAL pre-freeze audit; manual semantic review still required; no external review requests'})


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['audit'])
    parser.add_argument('--source',default='reviewed_cases.json')
    parser.add_argument('--output',default='audit')
    args=parser.parse_args()
    audit(args.source,args.output)
