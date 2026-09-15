"""Freeze locally reviewed synthetic questions before the first candidate request."""

from collections import Counter
from pathlib import Path
import time
import sqlglot
from sqlglot import exp

from eval.audit_final_mixed import ROOT, OUT, read, sha, history, sql_template, reference_result
from eval import run_300_clarification_regression as shared
from eval.scoring import digest, fingerprint, write_json
from app.tools.database import fetch_all


def semantic_shape(sql):
    tree=sqlglot.parse_one(sql_template(sql),read='mysql')
    for node in tree.walk():
        if isinstance(node,exp.Query):
            node.set('order',None)
            node.set('limit',None)
        if isinstance(node,exp.Round):
            node.replace(node.this.copy())
    return tree.sql(dialect='mysql',normalize=True)


def freeze():
    target=ROOT/'eval/final_mixed_cases.json'
    manifest=ROOT/'eval/final_mixed_freeze.json'
    assert not target.exists() and not manifest.exists()
    assert not (ROOT/'eval/final_mixed_events.jsonl').exists()
    lock=read(ROOT/'eval/conservative_gate_final_freeze.json')
    assert shared.git('rev-parse','HEAD')==lock['commit']
    assert all(sha(ROOT/name)==h for name,h in lock['hashes'].items())
    assert fingerprint(fetch_all)==lock['database']
    cases=read(OUT/'accepted_cases.json')
    assert len(cases)==200
    refs=read(OUT/'final_audit/reference_execution.json')
    assert all(r['ok'] for r in refs)
    assert not read(OUT/'final_audit/novelty.json')['duplicates']
    reference_by_id={r['id']:r for r in refs}
    reviews=[]
    amendments=[]
    for c in cases:
        if c['id']=='final_mixed_091':
            before={k:c[k] for k in ('question','reference_sql')}
            c['question']='不限时间，按退款原因统计已批准退款的总金额、最大单笔金额和最大单笔金额占该原因总额的比例。返回原因及上述三项指标，比率保留4位，按比率降序、原因升序。'
            c['reference_sql']="SELECT refund_reason,SUM(refund_amount) total_amount,MAX(refund_amount) max_amount,ROUND(MAX(refund_amount)/NULLIF(SUM(refund_amount),0),4) max_share FROM refunds WHERE refund_status='approved' GROUP BY refund_reason ORDER BY max_share DESC,refund_reason"
            amendments.append({'id':c['id'],'before':before,'after':{k:c[k] for k in before},
                'reason':'Order/limit/round-insensitive audit found a historical sum-only duplicate. Before any candidate call, replace with a refund concentration question; retain rejected draft.'})
        # Metadata wording corrections do not alter the frozen simulated answers.
        if c['id']=='final_mixed_178':
            c['ambiguity_alternatives']=['下单到退款记录日期间隔的算术平均','下单到退款记录日期间隔的中位数']
        if c['id']=='final_mixed_180':
            c['ambiguity_alternatives']=['同期间该品牌品类有效商品行销售金额','全历史该品牌品类有效商品行销售金额']
        if c['id']=='final_mixed_104':
            c['question']+=' 各原因的订单数与退款额都仅计父订单当前有效的已批准退款，比例分母仍为全站全部已批准退款额。'
        c['should_clarify']=c['kind']!='clear'
        assert c['should_clarify']==bool(c['simulated_answer'])
        assert not c['should_clarify'] or len(set(c['ambiguity_alternatives']))>=2
        c['ground_truth_result']=(reference_result(c['reference_sql']) if c['id']=='final_mixed_091'
                                 else reference_by_id[c['id']]['ground_truth_result'])
        assert reference_result(c['reference_sql'])==c['ground_truth_result']
        c['intended_slot']={'type':c['answer_slot'],'value':c['simulated_answer']}
        c['intended_meaning']=c['question'] if not c['should_clarify'] else c['question']+'\n预设单slot补充：'+c['simulated_answer']
        c['coverage_tags']=sorted(set([c['category']]+(['refund'] if 'refunds' in c['reference_sql'] else [])+
            (['join'] if 'JOIN' in c['reference_sql'].upper() else [])))
        reviews.append({'id':c['id'],'public_question_sha256':digest(c['question']),
            'reference_sql_sha256':digest(c['reference_sql']),
            'scope':'Local contract/schema review before any candidate output; not an external blind adjudicator',
            'single_missing_slot':c['answer_slot'],'reference_executed':True,
            'notes':'Explicit output columns, date scope, status population and grain reviewed; legitimate empty results retained',
            'source_audit':'curation_changes.json + final_reference_review_changes.json'})
    past,sources=history()
    shapes={}
    for x in past:
        try:
            shape=semantic_shape(x['reference_sql'])
        except (ValueError,sqlglot.errors.ParseError):
            continue
        shapes.setdefault(shape,[]).append({'source':x['source'],'id':x['id']})
    matches=[]
    for c in cases:
        shape=semantic_shape(c['reference_sql'])
        if shape in shapes:
            matches.append({'id':c['id'],'matches':list(shapes[shape])})
        shapes.setdefault(shape,[]).append({'source':'new_mixed','id':c['id']})
    # Any stronger normalized match requires local review before this can freeze.
    if matches:
        write_json(OUT/'semantic_shape_matches.json',matches)
        raise AssertionError('Pre-freeze semantic-shape matches require review')
    write_json(OUT/'semantic_review.json',{'candidate_calls':0,'cases':reviews,
        'pre_freeze_amendments':amendments,
        'historical_questions_screened':len(past),'sources':sources,'semantic_shape_matches':matches,
        'method':'Local question/reference review plus alias/literal normalization and order/limit/round-insensitive structural screening',
        'limitations':'Structural checks cannot prove novel meaning. Basic SQL operators and business metrics necessarily recur. This is internally authored synthetic evaluation, not an independently collected user sample.',
        'metadata_corrections':['178 observable refund date terminology','180 product-grain denominator terminology','104 explicit valid-parent numerator scope']})
    write_json(target,cases)
    model=shared.public_config()
    model.update({'workers_per_mode':1,'batch_size':1,'schedule':'Alternate OFF/ON order per case; all first turns then reviewed single-slot followups',
        'timeout_policy':'Frozen Gate JSON Object request timeout (5s connect,30s read); SQL wrapper unchanged SDK defaults; no evaluation retries; halt on infrastructure error',
        'second_user_turn':True})
    files=['eval/final_mixed_cases.json','eval/run_final_mixed.py','eval/run_300_clarification_regression.py',
        'eval/mixed_clarification_protocol.json','eval/conservative_gate_final_freeze.json',
        'eval/freeze_final_mixed.py','eval/final_mixed_authoring_revision_1/semantic_review.json',
        'eval/final_mixed_authoring_revision_1/final_audit/reference_execution.json']
    hashes={**lock['hashes'],**{name:sha(ROOT/name) for name in files}}
    write_json(manifest,{'status':'FINAL MIXED DATA FROZEN BEFORE CANDIDATE EXECUTION',
        'gate_freeze_commit':lock['commit'],'reference_date':lock['reference_date'],
        'database_seed':20260911,'original_300_benchmark_seed':lock['seed'],
        'new_mixed_authoring':'Fixed protocol, Qwen synthetic drafts plus local pre-freeze contract review; no reproducible model random seed guarantee',
        'database':lock['database'],'model_config':model,'workers':1,'hashes':hashes,
        'semantic_review_complete':True,'novelty_review_complete':True,
        'created_unix':time.time(),'candidate_calls':0,'kind_distribution':dict(Counter(c['kind'] for c in cases)),
        'difficulty_distribution':dict(Counter(c['difficulty'] for c in cases)),
        'empty_reference_results':sum(not c['ground_truth_result'] for c in cases),
        'disclosure':'Self-built synthetic mixed evaluation; 70/30 is not a live-traffic estimate. ON may receive one extra user answer; not equal-information model comparison.'})
    print('Frozen 200 cases, 140 clear + 20 time + 20 metric + 20 entity/filter; candidate calls=0',flush=True)


if __name__=='__main__':
    freeze()
