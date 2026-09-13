"""Frozen daily-business cases and shared result scoring for both agents."""

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-09-12"
VALID = "order_status IN ('paid','completed','shipped')"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def build_cases():
    cases = []

    def add(category, difficulty, question, sql, tables, spoken=None, ordered=False):
        cases.append(dict(id=f"daily_{len(cases)+1:03}", category=category,
                          difficulty=difficulty, question=f"以 {DATE} 为今天，{spoken or question}",
                          reference_sql=sql, expected_tables=tables, ordered=ordered,
                          paraphrase=spoken is not None, reference_date=DATE))

    cats = ['家用电器', '手机数码', '服饰鞋包', '母婴用品', '美妆个护']
    # 75 easy: single-table operational counts and monetary summaries.
    for cat in cats:
        for low in (80, 160, 320, 640, 1280):
            add('filtering_aggregation', 'easy', f'{cat}在售且标价至少{low}元的商品有多少种？',
                f"SELECT COUNT(*) AS n FROM products WHERE category='{cat}' AND is_active=1 AND list_price>={low}", ['products'],
                spoken=f'帮我数一下{cat}现在上架的商品，标价不低于{low}元的有多少种？' if low==80 else None)
    for city in ['上海市', '北京市', '南京市', '广州市', '成都市']:
        for year in (2022, 2023, 2024, 2025, 2026):
            add('filtering_aggregation', 'easy', f'{city}在{year}年注册的用户有多少人？',
                f"SELECT COUNT(*) AS n FROM users WHERE city='{city}' AND register_date>='{year}-01-01' AND register_date<'{year+1}-01-01'", ['users'])
    for method in ('alipay','wechat','card','cash',None):
        for status in ('paid','completed','shipped','cancelled','unpaid'):
            condition=f"payment_method='{method}' AND " if method else ''
            label=f'支付方式为{method}且' if method else ''
            add('filtering_aggregation', 'easy', f'{label}订单状态为{status}的订单实付金额合计是多少？所有符合上述条件的订单均统计。',
                f"SELECT ROUND(SUM(paid_amount),2) AS amount FROM orders WHERE {condition}order_status='{status}'", ['orders'])
    # 25 easy single-table rankings; 25 medium customer aggregate rankings.
    for cat in cats:
        for n in (3, 6, 9, 12, 15):
            add('top_k_ranking', 'easy', f'{cat}在售商品中标价最高的{n}种是哪些？返回名称和标价，同价按商品ID升序。',
                f"SELECT product_name,list_price FROM products WHERE category='{cat}' AND is_active=1 ORDER BY list_price DESC,product_id ASC LIMIT {n}", ['products'],
                spoken=f'{cat}现在卖的商品里，最贵的{n}种给我看看，要名称和标价；一样贵就按商品ID从小到大排。' if n==3 else None, ordered=True)
    for days in (21, 45, 75, 120, 180):
        for n in (3, 6, 9, 12, 15):
            add('top_k_ranking', 'medium', f'最近{days}天消费金额最高的{n}位客户是谁？返回客户名称和有效订单实付金额合计，金额相同按用户ID升序。',
                f"SELECT u.user_name,ROUND(SUM(o.paid_amount),2) AS amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY) GROUP BY u.user_id,u.user_name ORDER BY amount DESC,u.user_id ASC LIMIT {n}", ['users','orders'],
                spoken=f'近{days}天哪些客户花钱最多？给我前{n}位的名字和有效订单实付总额，同金额按用户ID从小到大。' if n==3 else None, ordered=True)
    # 25 easy windows, 20 monthly trends, 5 meaningful two-period comparisons.
    for days in (11, 18, 26, 37, 52):
        for expr, label in [('COUNT(*)','有效订单数'), ('ROUND(SUM(paid_amount),2)','销售额'), ('ROUND(AVG(paid_amount),2)','有效订单平均实付金额'), ('COUNT(DISTINCT user_id)','付费用户数'), ('ROUND(SUM(discount_amount),2)','有效订单优惠金额合计')]:
            add('time_trend','easy',f'最近{days}天的{label}是多少？',f"SELECT {expr} AS value FROM orders WHERE {VALID} AND order_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY)",['orders'],
                spoken=f'帮我看下近{days}天一共有多少笔有效订单。' if label=='有效订单数' else None)
    for start in ('2025-02-01','2025-05-01','2025-08-01','2025-11-01','2026-02-01'):
        for expr,label in [('COUNT(*)','有效订单数'),('ROUND(SUM(paid_amount),2)','销售额'),('ROUND(AVG(paid_amount),2)','平均实付金额'),('COUNT(DISTINCT user_id)','付费用户数')]:
            add('time_trend','medium',f'从{start}到2026-09-01之前，按自然月统计{label}，只统计有效订单。返回月份和指标，按月份升序。',
                f"SELECT DATE_FORMAT(order_date,'%Y-%m') AS month,{expr} AS value FROM orders WHERE {VALID} AND order_date>='{start}' AND order_date<'2026-09-01' GROUP BY month ORDER BY month",['orders'],ordered=True)
    for month in (3,4,5,6,7):
        add('time_trend','hard',f'比较2026年{month}月和上一个自然月的销售额，返回本月销售额、上月销售额和增长率（小数保留4位），金额保留2位。',
            f"SELECT ROUND(SUM(CASE WHEN MONTH(order_date)={month} THEN paid_amount ELSE 0 END),2) AS current_amount,ROUND(SUM(CASE WHEN MONTH(order_date)={month-1} THEN paid_amount ELSE 0 END),2) AS previous_amount,ROUND(SUM(CASE WHEN MONTH(order_date)={month} THEN paid_amount ELSE 0 END)/NULLIF(SUM(CASE WHEN MONTH(order_date)={month-1} THEN paid_amount ELSE 0 END),0)-1,4) AS growth FROM orders WHERE {VALID} AND order_date>='2026-{month-1:02}-01' AND order_date<'2026-{month+1:02}-01'",['orders'])
    # 33 medium joins across two tables, five HAVING cases.
    for days in (14,28,42,56,84,112,140,168,196,224,252):
        for dimension in ('city','province','user_level'):
            label={'city':'城市','province':'省份','user_level':'用户等级'}[dimension]
            add('one_two_table_join','medium',f'最近{days}天按{label}统计有效订单数和销售额，返回{label}及两个指标。',
                f"SELECT u.{dimension},COUNT(*) AS n,ROUND(SUM(o.paid_amount),2) AS amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} AND o.order_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY) GROUP BY u.{dimension}",['users','orders'],
                spoken=f'近{days}天各城市成交怎么样？给我城市、有效订单笔数和实付总额。' if dimension=='city' and days<=84 else None)
    for minimum in (5000,10000,15000,20000,25000):
        add('one_two_table_join','hard',f'找出有效订单消费总额至少{minimum}元且有效订单至少3笔的客户，返回客户ID、名称、订单数和消费总额，按用户ID升序最多100位。',
            f"SELECT u.user_id,u.user_name,COUNT(*) AS n,ROUND(SUM(o.paid_amount),2) AS amount FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} GROUP BY u.user_id,u.user_name HAVING SUM(o.paid_amount)>={minimum} AND COUNT(*)>=3 ORDER BY u.user_id LIMIT 100",['users','orders'],ordered=True)
    # 22 medium refund analyses; 3 hard approval rates.
    for days in (16,32,48,64,80,96,128,160,192,240,300):
        for dim in ('refund_reason','product_id'):
            label='退款原因' if dim=='refund_reason' else '商品ID'
            suffix='按商品ID升序，最多100种商品。' if dim=='product_id' else ''
            sql_suffix=' ORDER BY product_id LIMIT 100' if dim=='product_id' else ''
            add('refund_customer_product','medium',f'最近{days}天按{label}统计已通过退款金额和退款记录数，返回{label}和两个指标。{suffix}',
                f"SELECT {dim},ROUND(SUM(refund_amount),2) AS amount,COUNT(*) AS n FROM refunds WHERE refund_status='approved' AND refund_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY) GROUP BY {dim}{sql_suffix}",['refunds'],
                spoken=f'近{days}天钱都因为什么退的？按退款原因列出已通过的退款总额和记录数。' if dim=='refund_reason' and days<=80 else None)
    for days in (55,110,220):
        add('refund_customer_product','hard',f'最近{days}天各退款原因的退款通过率是多少？分母为该原因全部退款记录数，分子为approved记录数，保留4位小数。',
            f"SELECT refund_reason,ROUND(SUM(refund_status='approved')/COUNT(*),4) AS rate FROM refunds WHERE refund_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY) GROUP BY refund_reason",['refunds'])
    # 12 hard but practical exclusion queries, two tables only.
    for days in (35,70,105,175):
        for minimum in (800,1600,3200):
            add('complex','hard',f'最近{days}天实付至少{minimum}元的有效订单中，哪些没有任何已通过退款？返回订单ID和实付金额，按订单ID升序最多100条。',
                f"SELECT o.order_id,o.paid_amount FROM orders o WHERE o.{VALID} AND o.paid_amount>={minimum} AND o.order_date>=DATE_SUB('{DATE}',INTERVAL {days} DAY) AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id=o.order_id AND r.refund_status='approved') ORDER BY o.order_id LIMIT 100",['orders','refunds'],ordered=True)
    return cases


def fingerprint(fetch):
    return {table: digest(fetch(f'SELECT * FROM {table} ORDER BY {key}')) for table,key in
            [('users','user_id'),('products','product_id'),('orders','order_id'),
             ('order_items','order_item_id'),('refunds','refund_id'),('core_table','id'),('core_field','id')]}


def freeze():
    sys.path.insert(0,str(ROOT))
    from app.tools.database import fetch_all
    path=ROOT/'eval/daily_business_cases.json'
    if path.exists():
        raise RuntimeError('Cases already frozen; refusing overwrite')
    cases=build_cases()
    protocol=json.loads((ROOT/'eval/daily_business_protocol.json').read_text())
    assert len(cases)==250 and sum(c['paraphrase'] for c in cases)==30
    assert dict(Counter(c['difficulty'] for c in cases))==protocol['difficulty_counts']
    assert dict(Counter(c['category'] for c in cases))==protocol['category_counts']
    assert len({c['question'] for c in cases})==250
    before=fingerprint(fetch_all)
    for case in cases:
        case['expected_result']=fetch_all(case['reference_sql'])
        assert len(case['expected_result'])<=200
    assert before==fingerprint(fetch_all),'Database changed during ground truth generation'
    write_json(path,cases)
    write_json(ROOT/'eval/daily_business_manifest.json',dict(cases_sha256=digest(cases),database=before,
        scoring='Exact row/column counts; column aliases ignored; numeric abs tolerance 0.005, no relative tolerance; ordered cases check row order; unordered rows matched as multisets; successful workflow required.',
        empty_reference_count=sum(not c['expected_result'] for c in cases)))
    print(json.dumps(dict(cases=len(cases),paraphrase=30,empty=sum(not c['expected_result'] for c in cases))))


def same_value(a,b):
    if a is None or b is None:
        return a is b
    if isinstance(a,(int,float)):
        try:
            return math.isclose(float(a),float(b),rel_tol=0,abs_tol=0.005)
        except (ValueError,TypeError):
            return False
    return str(a)==str(b)


def compare(expected,actual,ordered=False):
    if len(expected)!=len(actual):
        return False
    if not expected:
        return True
    # A single global column permutation permits aliases and output order changes.
    from itertools import permutations
    width=len(expected[0])
    if any(len(r)!=width for r in actual):
        return False
    e=[list(r.values()) for r in expected]
    a=[list(r.values()) for r in actual]
    for permutation in permutations(range(width)):
        remaining=list(a)
        valid=True
        for row in e:
            choices=range(min(1,len(remaining))) if ordered else range(len(remaining))
            match=next((i for i in choices if all(same_value(x,remaining[i][j]) for x,j in zip(row,permutation))),None)
            if match is None:
                valid=False
                break
            remaining.pop(match)
        if valid:
            return True
    return False


if __name__=='__main__':
    freeze()
