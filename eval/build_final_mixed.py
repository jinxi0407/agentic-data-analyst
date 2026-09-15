"""Isolated benchmark authoring. No Gate or historical-result imports/inputs."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.tools.database import fetch_all
from app.tools.qwen import generate_text
from eval.scoring import digest, fingerprint, write_json
from eval.strong_baseline import BUSINESS_CONTEXT, schema_context
from eval.strong_baseline_v2 import STATIC_SCHEMA_METADATA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eval/final_mixed_authoring_revision_1'
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
    ambiguity_alternatives: list[str] = Field(default_factory=list)
    semantic_signature: str
    reference_sql: str
    ordered: bool


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    cases: list[Item]


INSTRUCTION = """生成中文日常业务评测草稿。question 必须为中文，不要输出英文问题。
clear 题的 simulated_answer 必须是空字符串，绝不能在该字段编造查询结果或数值答案。
本批只能围绕 coverage_focus 出题。previous_signatures 是禁止重复的旧草稿意图，不是示例，不要模仿。
同一查询只改城市、数值、时间字面值、LIMIT数量或同义改写不算新题。
每题需要不同的实际业务任务/统计粒度/字段组合。避免每批重复总销售额、付费人数等固定十题。
question 必须明确要返回的列；只返回指定列。目录/明细列表必须在问题中指定最多100行及稳定排序。
Author a synthetic Chinese daily-business analytics evaluation, not an Agent.
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
Use only supplied metadata literals. Reference date is fixed at 2026-09-12.
Dates must be explicit in the reference SQL and intended answer, NOT in the original
question when the deliberately missing slot is time. Never disclose that missing value
in an ambiguous question. ambiguity_alternatives must contain two materially different
reasonable choices for ambiguous items; clear items use an empty list.
Retain legitimate empty results; do not select questions based on result size or accuracy.
"""

# Coverage comes solely from public demo schema and the protocol, not Gate diagnostics.
FOCI = [
    'users 用户档案：gender/is_vip/user_level 与城市省份的构成、比例和分布，不涉及订单',
    'users 注册分析：register_date 的日历分组、注册间隔、会员等级及性别交叉分布',
    'products 商品目录：list_price/cost_price/is_active 的价格区间、差额、品牌品类分布',
    'products 上架分析：launch_date 的年月/季度队列，品类、品牌与价格统计',
    'orders 全状态订单：order_status/payment_method/order_date 的构成、次数、交叉分组',
    'orders 金额结构：gross_amount/discount_amount/paid_amount 的订单级统计与明确比例，不连接明细',
    'users+orders 客户交易频次：首末订单、有效订单次数、支付方式数及客户分组统计',
    'order_items 商品行：quantity/unit_price/discount_amount/item_amount 的行级分布与订单内汇总',
    'products+order_items+orders 商品组合：跨品牌品类的销量结构、购买覆盖、价格带及订单覆盖',
    'refunds 售后流程：refund_status/refund_reason/refund_date 的分布、金额、日历统计',
    'refunds+orders 售后关联：订单支付方式/状态与退款记录的关系，独立聚合避免金额重复',
    '日历业务对比：分别对注册、上架、订单、退款作相邻明确期间对比；每题只一个对象',
    '业务覆盖和缺失：无订单用户、无购买商品、无退款订单等 EXISTS/NOT EXISTS 查询，正常日常分析',
    '正常口语改写：围绕会员构成、支付结构、商品价差、售后原因、注册队列，保持指标列和时间明确',
    '仅时间歧义：用户注册、商品上架、订单数量、支付方式构成、会员分布等不同业务，唯一缺失slot是期间',
    '仅时间歧义：退款原因、退款状态、订单金额构成、商品行折扣等不同业务，唯一缺失slot是期间',
    '仅指标歧义：客户/地区/品牌的业务贡献比较，数量与金额是合理不同解释，其余过滤维度时间明确',
    '仅指标歧义：订单或商品的未定义评价/比例，分子分母或统计对象有两种合理解释，其他条件明确',
    '仅实体/过滤歧义：用户分组的限定值尚未说明，统计指标、时间、列数、其他条件都明确',
    '仅实体/过滤歧义：商品范围或售后筛选值尚未说明，指标时间和其他条件明确，无未定义业务概念',
]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_batch(raw, kind):
    items = Batch.model_validate_json(raw).cases
    assert len(items) == 10, 'Exactly ten items are required'
    for x in items:
        assert x.kind == kind, 'Every kind must equal the requested kind'
        assert re.search('[\u4e00-\u9fff]',x.question), 'Questions must be in Chinese'
        assert x.intended_meaning.strip() and x.semantic_signature.strip()
        if kind == 'clear':
            assert x.answer_slot == 'none' and x.simulated_answer == '', (
                'Clear cases require answer_slot none and simulated_answer empty string; never invent result values')
        else:
            assert x.answer_slot in ({'entity','filter'} if kind=='entity_filter' else {kind})
            assert x.simulated_answer.strip(), 'Ambiguous cases need one slot answer'
            assert len(set(x.ambiguity_alternatives))>=2, 'Ambiguous cases need two distinct material alternatives'
    return items


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
            request = {'allowed_inputs':packet, 'kind':kind, 'count':10,'coverage_focus':FOCI[i],
                       'previous_signatures':[x['semantic_signature'] for x in all_cases]}
            mode = ('本批10题都是clear，问题信息完整，simulated_answer必须为空字符串。' if kind=='clear' else
                    '本批10题全部是'+kind+'单歧义题，不是明确题。question只缺少该关键slot，不能写入该slot的答案。'
                    'simulated_answer必须非空，只补充这一slot；时间回答应给完整期间，不是孤立起始日。'
                    'ambiguity_alternatives必须列出至少两种合理且有实质差别的解释。'
                    '已有明确最近N天/月、昨天、某年月的问题不属于时间歧义。reference_sql采用预设回答之后的意图。')
            base_messages = [{'role':'system','content':INSTRUCTION+'\n'+mode+'\nResponse JSON Schema:\n'+json.dumps(Batch.model_json_schema(),ensure_ascii=False)},
                        {'role':'user','content':json.dumps(request,ensure_ascii=False)}]
            messages = base_messages
            for attempt in range(5):
                suffix = '' if attempt == 0 else f'_revision_{attempt}'
                request_file = OUT / f'batch_{i:02d}{suffix}_request.json'
                raw_file = OUT / f'batch_{i:02d}{suffix}_raw.json'
                if raw_file.exists():
                    raw = read(raw_file)['raw']
                else:
                    assert not request_file.exists(), 'Unobserved authoring call; do not duplicate'
                    write_json(request_file,messages)
                    raw = generate_text(messages,temperature=.7,
                        response_format={'type':'json_object'},request_timeout=(5,120))
                    write_json(raw_file,{'raw':raw})
                try:
                    items = validate_batch(raw,kind)
                    from eval.audit_final_mixed import sql_template
                    seen = {sql_template(x['reference_sql']) for x in all_cases}
                    signatures = {x['semantic_signature'] for x in all_cases}
                    for item in items:
                        key = sql_template(item.reference_sql)
                        assert key not in seen and item.semantic_signature not in signatures, (
                            'Duplicate logical task/template. Create distinct tasks within coverage_focus; do not copy previous_signatures.')
                        seen.add(key)
                        signatures.add(item.semantic_signature)
                except (ValueError,AssertionError) as exc:
                    issue = str(exc)
                    write_json(OUT/f'batch_{i:02d}{suffix}_rejection.json',
                        {'reason':issue,'candidate_calls':0,'stage':'pre-benchmark authoring format validation'})
                    if attempt == 4:
                        raise
                    messages = base_messages + [{'role':'user','content':
                        '前一份未进入评测的草稿不合规。请重新按本批协议输出10题JSON，不能把明确题标成歧义题。'
                        +mode+' 校验错误：'+issue}]
                else:
                    break
            write_json(result_file, [x.model_dump() for x in items])
        assert len(items) == 10 and all(x.kind == kind for x in items)
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
