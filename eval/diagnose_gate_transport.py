"""Small serial Qwen diagnostics; no benchmark or SQL-engine execution."""

import argparse
import ast
from contextlib import ExitStack
from datetime import date
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import time
from unittest.mock import patch

import requests
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

from app.agent import scoped_clarification as gate
from app.config import settings
from app.tools import qwen
from eval.scoring import write_json

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = date(2026, 9, 12)
CLEAR = "最近30天销售额是多少？"
AMBIGUOUS = "最近销售怎么样？"
OUT = ROOT / 'eval/gate_transport_diagnostics'


def save_acceptance():
    from eval.conservative_gate_experiment import verify_engine
    frozen = verify_engine()
    checkpoint = 'f780857'
    old = subprocess.check_output(['/usr/bin/git','show',checkpoint+':app/agent/scoped_clarification.py'],cwd=ROOT).decode()
    current = Path(gate.__file__).read_text()
    def policy(source):
        result = {}
        for node in ast.parse(source).body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name != 'decide':
                result[node.name] = ast.dump(node)
            elif isinstance(node,ast.Assign):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id in ('PROMPT','FOLLOWUP_PROMPT','Slot'):
                        result[target.id] = ast.dump(node)
        return result
    assert policy(old) == policy(current), 'Gate decision policy or validators changed'
    final = json.loads((OUT/'09_json_object_serial_10.json').read_text())
    rows = final['requests']
    assert len(rows) == 10 and all(r['success'] for r in rows)
    assert all(r['decision'] == ('proceed' if r['kind']=='clear' else 'clarify') for r in rows)
    assert all(len(r['http_requests']) == len(r['model_calls']) == 1 for r in rows)
    assert final['gate_sha256'] == hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest()
    assert final['qwen_wrapper_sha256'] == hashlib.sha256(Path(qwen.__file__).read_bytes()).hexdigest()
    metrics = {'checkpoint':checkpoint,'gate_policy_ast_unchanged':True,'sql_engine_unchanged':True,
        'database':frozen['database'],'cases_sha256':frozen['cases_file_sha256'],
        'completed':len(rows),'clear_proceed':sum(r['kind']=='clear' for r in rows),
        'ambiguous_clarify':sum(r['kind']=='ambiguous' for r in rows),
        'mean_s':statistics.mean(r['total_s'] for r in rows),
        'minimum_s':min(r['total_s'] for r in rows),'maximum_s':max(r['total_s'] for r in rows),
        'model_calls':10,'http_requests':10,'connections':sum(len(r['connections']) for r in rows),
        'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(OUT.glob('0*.json'))},
        'large_evaluation_run':False,'new_mixed_cases_generated':False,
        'scope':'Transport smoke on two explicit diagnostic questions, not accuracy or load validation'}
    write_json(OUT/'acceptance.json',metrics)
    print(json.dumps({k:v for k,v in metrics.items() if k not in ('files','database')},ensure_ascii=False))


def summarize_body(body):
    data = json.loads(body)
    messages = data.get('input', {}).get('messages', [])
    content = ''.join(m.get('content', '') for m in messages)
    parameters = data.get('parameters', {})
    return {'model': data.get('model'), 'body_bytes': len(body),
            'message_count': len(messages), 'message_characters': len(content),
            'token_estimate_range': [len(content)//4, len(content)],
            'token_estimate_note': 'Rough mixed-language bounds, not tokenizer counts; actual usage recorded separately',
            'structured_output_mode': parameters.get('response_format', {}).get('type'),
            'parameter_names': sorted(parameters),
            'max_tokens': parameters.get('max_tokens', 'server default'),
            'stream_parameter': parameters.get('stream', False),
            'schema_context_occurrences': content.count('CREATE TABLE users'),
            'business_context_occurrences': content.count('Business metric definitions:'),
            'static_metadata_occurrences': content.count('Static schema metadata:'),
            'body_sha256': hashlib.sha256(body).hexdigest()}


def measured(kind, index, variant):
    record = {'kind': kind, 'index': index, 'variant': variant,
              'connections': [], 'http_requests': [], 'model_calls': []}
    sdk = qwen._require_dashscope()
    sdk_call = sdk.Generation.call
    session_send = requests.Session.send
    connect = HTTPSConnection.connect
    make_request = HTTPSConnectionPool._make_request

    def timed_connect(self):
        started = time.perf_counter()
        try:
            return connect(self)
        finally:
            record['connections'].append({'dns_tcp_tls_s': round(time.perf_counter()-started,6)})

    def timed_request(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            response = make_request(self, *args, **kwargs)
            record['http_requests'][-1]['headers_after_s'] = round(time.perf_counter()-started,6)
            return response
        except Exception as exc:
            record['http_requests'][-1]['transport_exception'] = type(exc).__name__
            raise

    def timed_send(self, request, **kwargs):
        meta = summarize_body(request.body)
        meta.update(timeout=kwargs.get('timeout'), stream=kwargs.get('stream',False))
        record['http_requests'].append(meta)
        started = time.perf_counter()
        try:
            response = session_send(self, request, **kwargs)
            meta.update(http_status=response.status_code,
                        requests_headers_elapsed_s=response.elapsed.total_seconds())
            if response.status_code != 200:
                try:
                    meta['api_error_code'] = response.json().get('code')
                except ValueError:
                    pass
            return response
        except Exception as exc:
            meta['exception'] = type(exc).__name__
            raise
        finally:
            meta['total_http_s'] = round(time.perf_counter()-started,6)

    def bounded_call(**kwargs):
        if variant != 'production':
            kwargs['request_timeout'] = (5,30)
        if variant in ('json_object_schema','schema_in_message'):
            schema = kwargs.get('response_format',{}).get('json_schema',{}).get('schema')
            schema = schema or gate.InitialDecision.model_json_schema()
            kwargs['messages'] = [dict(m) for m in kwargs['messages']]
            base = kwargs['messages'][0]['content'].split('\nResponse JSON Schema:\n')[0]
            kwargs['messages'][0]['content'] = base + '\nResponse JSON Schema:\n' + json.dumps(schema,ensure_ascii=False)
            if variant == 'schema_in_message':
                kwargs['response_format'] = {'type':'json_schema','json_schema':{
                    'name':'clarification_decision','strict':True,'schema':schema}}
        if variant in ('json_object','json_object_schema'):
            kwargs['response_format'] = {'type':'json_object'}
        if variant == 'bounded_output':
            kwargs['max_tokens'] = 512
        if variant == 'fresh_session':
            from dashscope.api_entities.http_request import close_shared_sync_session
            close_shared_sync_session()
        response = sdk_call(**kwargs)
        if response.status_code == 200:
            choices = (response.get('output') or {}).get('choices') or []
            if choices:
                text = choices[0].get('message', {}).get('content', '')
                record.setdefault('outputs', []).append({'characters':len(text),
                    'whitespace_fraction':sum(x.isspace() for x in text)/max(1,len(text)),
                    'finish_reason':choices[0].get('finish_reason')})
        return response

    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(HTTPSConnection,'connect',timed_connect))
        stack.enter_context(patch.object(HTTPSConnectionPool,'_make_request',timed_request))
        stack.enter_context(patch.object(requests.Session,'send',timed_send))
        stack.enter_context(patch.object(sdk.Generation,'call',bounded_call))
        with qwen.capture_usage() as usage:
            try:
                if kind == 'minimal':
                    text = qwen.generate_text([{'role':'user','content':'只回复 OK'}],temperature=0)
                    record['reply_is_ok'] = text.strip().upper() == 'OK'
                else:
                    d = gate.decide(CLEAR if kind == 'clear' else AMBIGUOUS,REFERENCE)
                    record.update(decision=d.decision,missing_slots=d.missing_slots)
                record['success'] = True
            except Exception as exc:
                record.update(success=False, error_type=type(exc).__name__)
            record['model_calls'] = usage
    record['total_s'] = round(time.perf_counter()-started,6)
    record['first_response_note'] = 'headers_after_s measures first response headers, not first streamed token; actual mode is non-streaming'
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument('step', choices=['minimal','clear','ambiguous','serial','acceptance'])
    p.add_argument('--variant', choices=['bounded','production','json_object','json_object_schema','schema_in_message','bounded_output','fresh_session'], default='bounded')
    p.add_argument('--label')
    args = p.parse_args()
    if args.step == 'acceptance':
        save_acceptance()
        return
    assert args.label, '--label is required for live diagnostics'
    assert args.label.replace('_','').replace('-','').isalnum()
    OUT.mkdir(exist_ok=True)
    path = OUT / (args.label+'.json')
    assert not path.exists(), 'Preserve prior diagnostic evidence'
    logging.getLogger('dashscope').setLevel(logging.CRITICAL)
    result = {'step':args.step,'variant':args.variant,'concurrency':1,
              'sdk_version':version('dashscope'), 'qwen_wrapper_sha256':hashlib.sha256(Path(qwen.__file__).read_bytes()).hexdigest(),
              'gate_sha256':hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest(),
              'proxy_env_present':{k:bool(os.getenv(k)) for k in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']},
              'requests':[]}
    kinds = ['clear','ambiguous']*5 if args.step == 'serial' else [args.step]
    for i,kind in enumerate(kinds):
        result['requests'].append(measured(kind,i+1,args.variant))
        write_json(path,result)
        r = result['requests'][-1]
        print(json.dumps({'index':i+1,'kind':kind,'success':r['success'],
                          'decision':r.get('decision'),'total_s':r['total_s'],
                          'http':r['http_requests']},ensure_ascii=False),flush=True)
        if not r['success']:
            break


if __name__ == '__main__':
    main()
