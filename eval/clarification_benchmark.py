"""Predeclared clarification fixtures; references execute before model evaluation."""

import argparse
from datetime import date, timedelta
from pathlib import Path
import subprocess

from app.tools.database import fetch_all
from eval.scoring import digest, fingerprint, write_json

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "2026-09-12"
VALID = "order_status IN ('paid','completed','shipped')"
FROZEN_FILES = ["app/agent/clarification.py", "app/agent/production.py", "eval/strong_baseline.py",
                "eval/strong_baseline_v2.py", "app/tools/qwen.py", "app/tools/guardrail.py"]


def code_digest():
    return digest({name: (ROOT / name).read_text() for name in FROZEN_FILES})


def fixtures(split):
    """Paired business intents; ambiguous versions deliberately omit one critical input."""
    if split == "holdout":
        from eval.clarification_holdout_design import holdout_fixtures
        return holdout_fixtures()
    values = range(4)
    offset = 0
    categories = ["手机数码", "家用电器", "服饰鞋包", "母婴用品", "美妆个护", "运动户外", "食品生鲜"]
    cities = ["上海", "杭州", "北京", "广州", "深圳", "成都", "武汉", "南京", "苏州"]
    cases = []
    for i in values:
        j = i + offset
        days = 11 + j * 6
        start = (date.fromisoformat(REFERENCE) - timedelta(days=days)).isoformat()
        category = categories[j % len(categories)]
        city = cities[j % len(cities)]
        top = 3 + j
        amount = 2000 + j * 700
        price = 180 + j * 90
        period = f"order_date >= '{start}' AND order_date < '{REFERENCE}'"
        families = [
            ("time", f"最近{days}天（不含今天）的有效订单销售额是多少？只返回总额。",
             "最近有效订单销售额是多少？只返回总额。", f"最近{days}天，不含今天。",
             f"SELECT ROUND(SUM(paid_amount),2) AS total FROM orders WHERE {VALID} AND {period}"),
            ("metric", f"{category}商品共卖出多少件？按有效订单统计，只返回数量。",
             f"{category}商品销售表现是多少？只返回一个总计。", "按有效订单的销量，也就是销售数量统计，全部历史。",
             f"SELECT SUM(i.quantity) AS total FROM order_items i JOIN orders o ON i.order_id=o.order_id JOIN products p ON i.product_id=p.product_id WHERE o.{VALID} AND p.category='{category}'"),
            ("business_definition", f"有效订单累计实付金额超过{amount}元的客户有多少个？只返回人数。",
             f"消费水平较高的客户有多少个？只返回人数。", f"有效订单累计实付金额超过{amount}元，全部历史。",
             f"SELECT COUNT(*) AS total FROM (SELECT user_id FROM orders WHERE {VALID} GROUP BY user_id HAVING SUM(paid_amount)>{amount}) t"),
            ("filter", f"标价高于{price}元的在售商品有多少个？只返回数量。",
             "价格偏高的在售商品有多少个？只返回数量。", f"标价高于{price}元。",
             f"SELECT COUNT(*) AS total FROM products WHERE is_active=1 AND list_price>{price}"),
            ("entity", f"{city}客户的有效订单有多少笔？只返回订单数。",
             f"我们区域的客户有多少笔有效订单？只返回订单数。", f"客户城市为{city}，统计全部历史。",
             f"SELECT COUNT(*) AS total FROM users u JOIN orders o ON u.user_id=o.user_id WHERE u.city='{city}' AND o.{VALID}"),
            ("metric", f"按累计有效订单消费金额降序，列出前{top}位客户的用户ID和消费金额，金额相同时按用户ID升序。",
             f"列出前{top}位表现最好的客户，返回用户ID和排名指标，指标相同时按用户ID升序。",
             "按全部历史有效订单累计实付金额从高到低排名，金额保留两位小数。",
             f"SELECT user_id,ROUND(SUM(paid_amount),2) AS amount FROM orders WHERE {VALID} GROUP BY user_id ORDER BY amount DESC,user_id ASC LIMIT {top}"),
            ("time", f"最近{days}天（不含今天）已批准退款总额是多少？只返回总额。",
             "近期已批准退款总额是多少？只返回总额。", f"最近{days}天，不含今天，使用退款时间。",
             f"SELECT ROUND(SUM(refund_amount),2) AS total FROM refunds WHERE refund_status='approved' AND refund_date>='{start}' AND refund_date<'{REFERENCE}'"),
            ("business_definition", f"全部历史有效订单次数至少{top}次的客户有多少人？只返回人数。",
             "经常购买的客户有多少人？只返回人数。", f"全部历史有效订单次数至少{top}次。",
             f"SELECT COUNT(*) AS total FROM (SELECT user_id FROM orders WHERE {VALID} GROUP BY user_id HAVING COUNT(*)>={top}) t"),
            ("filter", f"列出有效订单数至少{top}的城市及其有效订单数，按城市升序。",
             "列出订单比较多的城市及其有效订单数，按城市升序。", f"全部历史有效订单数至少{top}。",
             f"SELECT u.city,COUNT(*) AS total FROM users u JOIN orders o ON u.user_id=o.user_id WHERE o.{VALID} GROUP BY u.city HAVING COUNT(*)>={top} ORDER BY u.city"),
            ("time", f"从{start}到2026-09-11（包含首尾日），每天有效订单销售额是多少？返回日期和金额并按日期升序。",
             "这段时间每天有效订单销售额是多少？返回日期和金额并按日期升序。",
             f"从{start}到2026-09-11，包含首尾日。",
             f"SELECT DATE(order_date) AS day,ROUND(SUM(paid_amount),2) AS amount FROM orders WHERE {VALID} AND {period} GROUP BY DATE(order_date) ORDER BY day"),
        ]
        for family, (kind, clear, ambiguous, answer, sql) in enumerate(families):
            # The context suffix makes repeated open-ended intents distinct without defining the missing input.
            ambiguous = f"运营报表第{j + 1}组：{ambiguous}"
            for needs, question in [(False, clear), (True, ambiguous)]:
                cases.append(dict(id=f"{split}-{j}-{family}-{'a' if needs else 'c'}", question=question,
                    should_clarify=needs, ambiguity_type=kind if needs else "none",
                    clarification_answer=answer if needs else None, resolved_question=clear,
                    reference_sql=sql, ordered="ORDER BY" in sql, family=family,
                    ground_truth_result=[]))
    return cases


def create(split, freeze):
    path = ROOT / f"eval/clarification_{split}.json"
    if path.exists():
        raise SystemExit("Dataset already exists; refusing to overwrite frozen questions")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if split == "holdout":
        if not freeze or not head.startswith(freeze):
            raise SystemExit("Holdout requires the current frozen gate commit")
        changed = subprocess.check_output(["git", "diff", "HEAD", "--", *FROZEN_FILES], cwd=ROOT, text=True)
        if changed:
            raise SystemExit("Gate changes exist after freeze")
    before = fingerprint(fetch_all)
    cases = fixtures(split)
    for case in cases:
        case["ground_truth_result"] = fetch_all(case["reference_sql"])
    assert before == fingerprint(fetch_all), "Database changed while creating ground truth"
    assert len({c["question"] for c in cases}) == len(cases)
    write_json(path, cases)
    write_json(path.with_name(path.stem + "_manifest.json"), {
        "cases_sha256": digest(cases), "database": before, "reference_date": REFERENCE,
        "gate_code_sha256": code_digest(), "freeze_commit": head,
        "count": len(cases), "clear": len(cases)//2, "ambiguous": len(cases)//2,
        "chat_model": "qwen-plus", "gate_temperature": 0, "sql_temperature": 0.05,
        "max_execution_retry": 2, "max_clarification_rounds": 1,
        "embedding": "not used by the frozen static-schema production path",
        "scoring_sha256": digest((ROOT / "eval/scoring.py").read_text()),
        "protocol": "Decision plus strict result comparison; simulated answers for v1.1 only. Failures retained. No post-holdout tuning.",
    })
    print(f"Frozen {split}: {len(cases)} cases, ground truth generated read-only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("split", choices=["dev", "holdout"])
    parser.add_argument("--freeze")
    args = parser.parse_args()
    create(args.split, args.freeze)
