from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest


def test_clarification_form_preserves_context(monkeypatch):
    import requests
    sent = []
    responses = iter([
        {"status": "needs_clarification", "clarification_question": "最近7天还是30天？",
         "clarification_context": {"original_question": "最近销售额"}},
        {"status": "success", "result": [{"amount": 12}], "sql": "SELECT 12", "trace": [], "latency_ms": 100},
    ])
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(ok=True))
    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        payload = next(responses)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(requests, "post", post)
    view = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/app.py")).run(timeout=30)
    next(toggle for toggle in view.toggle if toggle.label == "启用一次主动澄清").set_value(True).run()
    view.text_area[0].set_value("最近销售额").run()
    next(button for button in view.button if button.label == "开始分析").click().run(timeout=30)
    assert not view.exception
    view.text_input[0].set_value("30天").run()
    next(button for button in view.button if button.label == "继续分析").click().run(timeout=30)
    assert not view.exception
    assert sent[1]["clarification_answer"] == "30天"
    assert sent[0]["mode"] == sent[1]["mode"] == "clarify"
    assert sent[1]["question"] == "最近销售额"
    assert len(view.dataframe) == 1


def test_new_question_clears_pending_answer(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        body=kwargs['json'];sent.append(body)
        payload={'status':'needs_clarification','clarification_question':'哪个时间范围？',
                 'clarification_context':{'original_question':body['question']}}
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    assert not next(x for x in view.toggle if x.label=='启用一次主动澄清').value
    next(x for x in view.toggle if x.label=='启用一次主动澄清').set_value(True).run()
    view.text_area[0].set_value('第一个问题').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    view.text_input[0].set_value('不应串到新题的回答').run()
    view.text_area[0].set_value('第二个问题').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert not view.exception
    assert view.text_input[0].value==''
    assert view.session_state['payload']['clarification_context']['original_question']=='第二个问题'
    assert 'clarification_context' not in sent[1] and 'clarification_answer' not in sent[1]
