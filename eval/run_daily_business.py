"""Same isolated runner for the frozen Baseline and Final implementations."""

import argparse
import concurrent.futures
import fcntl
import importlib.util
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('daily_scoring',ROOT/'eval/daily_business.py')
scoring=importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--implementation',required=True)
    parser.add_argument('--label',choices=['baseline','final'],required=True)
    args=parser.parse_args()
    sys.path.insert(0,args.implementation)
    from app.agent.workflow import run_question
    from app.config import settings
    from app.tools.database import fetch_all
    assert settings.qwen_chat_model=='qwen-plus'
    assert settings.qwen_embedding_model=='text-embedding-v4'
    lock=(ROOT/f'eval/daily_{args.label}.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cases=json.loads((ROOT/'eval/daily_business_cases.json').read_text())
    manifest=json.loads((ROOT/'eval/daily_business_manifest.json').read_text())
    assert scoring.digest(cases)==manifest['cases_sha256']
    assert scoring.fingerprint(fetch_all)==manifest['database']
    checkpoint=ROOT/f'eval/daily_{args.label}_results.json'
    results=json.loads(checkpoint.read_text()) if checkpoint.exists() else []
    done={r['id'] for r in results}
    assert len(done)==len(results)

    def evaluate(case):
        started=time.perf_counter()
        try:
            state=run_question(case['question'])
        except Exception as exc:
            state={'status':'failed','execution_error':type(exc).__name__}
        actual=state.get('query_result',[])
        return dict(id=case['id'],category=case['category'],difficulty=case['difficulty'],
            paraphrase=case['paraphrase'],status=state.get('status'),
            correct=state.get('status')=='success' and scoring.compare(case['expected_result'],actual,case['ordered']),
            generated_sql=state.get('sql',''),actual_result=actual,
            retry_count=state.get('retry_count',0),intent_status=state.get('intent_status'),
            latency_ms=round((time.perf_counter()-started)*1000,2),
            trace=state.get('trace',[]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(evaluate,c):c for c in cases if c['id'] not in done}
        for future in concurrent.futures.as_completed(futures):
            result=future.result()
            results.append(result)
            scoring.write_json(checkpoint,sorted(results,key=lambda r:r['id']))
            print(f'{args.label}: {len(results)}/250 persisted',flush=True)
    assert scoring.fingerprint(fetch_all)==manifest['database']
    def accuracy(rows):
        return sum(r['correct'] for r in rows)/len(rows) if rows else None
    report=dict(label=args.label,total=len(results),accuracy=accuracy(results),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.implementation,text=True).strip(),
        cases_sha256=manifest['cases_sha256'],workers=4,
        average_latency_ms=statistics.mean(r['latency_ms'] for r in results),
        average_retry=statistics.mean(r['retry_count'] for r in results),
        category={c:accuracy([r for r in results if r['category']==c]) for c in sorted({r['category'] for r in results})},
        difficulty={d:accuracy([r for r in results if r['difficulty']==d]) for d in ['easy','medium','hard']},
        paraphrase_accuracy=accuracy([r for r in results if r['paraphrase']]),
        execution_repair_triggered=sum(r['retry_count']>0 for r in results),
        repaired_result_correct=sum(r['retry_count']>0 and r['correct'] for r in results),
        repaired_workflow_success=sum(r['retry_count']>0 and r['status']=='success' for r in results))
    scoring.write_json(ROOT/f'eval/daily_{args.label}_report.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
