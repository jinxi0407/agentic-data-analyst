import json
from datetime import date

import pytest
import sqlglot

from eval import audit_final_mixed as audit
from eval import build_final_mixed as author
from eval import run_final_mixed as runner


def item():
    return {'question':'统计各支付方式的订单数。','category':'aggregation','difficulty':'easy',
        'kind':'clear','intended_meaning':'按支付方式统计所有状态订单数量','simulated_answer':'',
        'answer_slot':'none','ambiguity_explanation':'','semantic_signature':'payment-all-status-count',
        'reference_sql':'SELECT payment_method,COUNT(*) FROM orders GROUP BY payment_method','ordered':False}


def test_authoring_rejects_result_as_clear_answer():
    x=item()
    x['simulated_answer']='42'
    with pytest.raises(AssertionError):
        author.validate_batch(json.dumps({'cases':[x]*10}),'clear')


def test_authoring_rejects_non_chinese_questions():
    x=item()
    x['question']='How many orders?'
    with pytest.raises(AssertionError):
        author.validate_batch(json.dumps({'cases':[x]*10}),'clear')


def test_authoring_valid_format():
    assert len(author.validate_batch(json.dumps({'cases':[item()]*10}),'clear'))==10


def test_template_catches_literal_and_alias_only_substitutions():
    a="SELECT u.city, COUNT(*) AS n FROM users u WHERE u.city='上海市' GROUP BY u.city ORDER BY n DESC LIMIT 5"
    b="SELECT x.city, COUNT(*) AS total FROM users x WHERE x.city='北京市' GROUP BY x.city ORDER BY total DESC LIMIT 9"
    assert audit.sql_template(a)==audit.sql_template(b)
    assert audit.sql_template(a)!=audit.sql_template(b.replace('COUNT(*)','SUM(user_id)'))


@pytest.mark.parametrize('sql',['DELETE FROM users','SELECT 1; DELETE FROM users',
    'SELECT * INTO OUTFILE \'x\' FROM users','SELECT * FROM mysql.user',
    'SELECT * FROM financial_agentic_rag.orders','SELECT * FROM core_field'])
def test_reference_cannot_execute_write(sql,monkeypatch):
    def forbidden_connection():
        pytest.fail('Unsafe SQL reached a database connection')
    monkeypatch.setattr(audit,'connection',forbidden_connection)
    with pytest.raises((AssertionError,sqlglot.errors.ParseError)):
        audit.reference_result(sql)


def test_candidate_interface_contains_no_oracle(monkeypatch):
    seen=[]
    monkeypatch.setattr(runner.gate,'direct',lambda question,reference:seen.append((question,reference,'off')))
    monkeypatch.setattr(runner.gate,'run_interactive',lambda question,reference_date:seen.append((question,reference_date,'on')))
    for mode in ['off','on']:
        runner.candidate('公开问题',date(2026,9,12),mode)
    assert seen==[('公开问题',date(2026,9,12),'off'),('公开问题',date(2026,9,12),'on')]


@pytest.mark.parametrize('asked,slot,eligible',[
    (['time'],'time',True),(['metric'],'time',True),(['time','metric'],'time',True),([], 'time',True),(['time'],'none',False)])
def test_answer_packet_exposes_only_corresponding_single_slot(asked,slot,eligible):
    case={'id':'a','question':'近期销售额','answer_slot':slot,'simulated_answer':'2026年8月',
          'reference_sql':'SECRET ORACLE','intended_meaning':'SECRET ORACLE','ground_truth_result':[42]}
    payload={'status':'needs_clarification','clarification_question':'哪个月？',
             'clarification_context':{'missing_slots':asked}}
    packet=runner.answer_packet(case,payload)
    assert packet['slot_eligible']==eligible
    assert packet['frozen_answer']==('2026年8月' if eligible else '')
    assert 'SECRET ORACLE' not in str(packet)


def test_unanswerable_question_never_receives_frozen_answer():
    p={'id':'a','actual_question':'哪个月？','slot_eligible':True,'frozen_answer':'2026年8月'}
    r={'id':'a','actual_question':'哪个月？','answerable':False,'reason':'Actual missing information is different'}
    assert runner.checked_answer(r,p) is None
    r['answerable']=True
    assert runner.checked_answer(r,p)=='2026年8月'
