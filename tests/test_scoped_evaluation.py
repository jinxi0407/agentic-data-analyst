from datetime import date

import pytest

from eval import run_scoped_clarification as runner


def test_candidate_receives_only_public_input(monkeypatch):
    calls=[]
    monkeypatch.setattr(runner,"direct",lambda q,ref:calls.append((q,ref)) or {})
    monkeypatch.setattr(runner,"run_interactive",lambda q,reference_date:calls.append((q,reference_date)) or {})
    reference=date(2026,9,12)
    runner.first_call("问题",reference,"baseline")
    runner.first_call("问题",reference,"first")
    assert calls==[("问题",reference),("问题",reference)]


def test_simulator_only_supplies_question_scoped_verbatim_answer():
    packet={"actual_question":"时间范围？","persona_answer":"2026年8月，包含整月。"}
    item={"actual_question":"时间范围？","reason":"只补被问时间","valid_question":True,
          "answer_segments":["2026年8月，包含整月。"]}
    assert runner.checked_answer(item,packet)==packet["persona_answer"]
    item["answer_segments"]=["按销量取前十名"]
    with pytest.raises(AssertionError): runner.checked_answer(item,packet)
    item.update(valid_question=False,answer_segments=[])
    assert runner.checked_answer(item,packet) is None


def test_percentages_preserve_denominators():
    assert runner.ratio(44,60)=={"n":44,"d":60,"percent":73.33}
    assert runner.ratio(0,0)=={"n":0,"d":0,"percent":None}
    assert runner.latency([1,None,2])["missing"]==1
