from datetime import date
import json

import pytest

from eval.audit_clarification_cities import ROOT, correct_literal
from eval import run_corrected_clarification as runner


def test_only_city_literal_changes():
    sql = "SELECT u.city,COUNT(*) FROM users u JOIN orders o ON o.user_id=u.user_id WHERE u.city='上海' AND o.paid_amount>123 GROUP BY u.city ORDER BY u.city"
    assert correct_literal(sql,"上海","上海市") == sql.replace("'上海'","'上海市'")


def test_question_is_the_only_case_input(monkeypatch):
    called = []
    monkeypatch.setattr(runner,"run_interactive",lambda question,**kwargs: called.append((question,kwargs)) or {"status":"success","result":[]})
    runner.first_call("question",date(2026,9,12),"v1_1")
    assert called==[("question",{"reference_date":date(2026,9,12)})]


def test_reply_projection_does_not_add_other_conditions():
    case={"clarification_answer":"最近19天，不含今天。按销售数量统计。"}
    first={"clarification_question":"最近是几天？"}
    reply={"asked_question":"最近是几天？","segments":["最近19天，不含今天"],
           "review_reason":"Only the requested time boundary is answered","answerable":True}
    assert runner.checked_reply(case,first,reply)=="最近19天，不含今天"
    with pytest.raises(AssertionError):
        runner.checked_reply(case,first,reply|{"segments":["最近30天"]})
    with pytest.raises(AssertionError):
        runner.checked_reply(case,first,reply|{"asked_question":"按什么指标？"})
    assert runner.checked_reply(case,first,reply|{"answerable":False,"segments":[]}) is None


def test_corrected_dataset_preserves_all_other_fields():
    original=json.loads((ROOT/"eval/clarification_holdout.json").read_text())
    revised=json.loads((ROOT/"eval/clarification_holdout_corrected.json").read_text())
    assert len(original)==len(revised)==120
    for old,new in zip(original,revised):
        assert {k:v for k,v in old.items() if k not in ("reference_sql","ground_truth_result")} == {
            k:v for k,v in new.items() if k not in ("reference_sql","ground_truth_result")}
        if old["reference_sql"]==new["reference_sql"]:
            assert old==new
