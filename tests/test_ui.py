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
    assert next(toggle for toggle in view.toggle if toggle.label == "自动判断是否澄清").value
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
    assert next(x for x in view.toggle if x.label=='自动判断是否澄清').value
    view.text_area[0].set_value('第一个问题').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    view.text_input[0].set_value('不应串到新题的回答').run()
    view.text_area[0].set_value('第二个问题').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert not view.exception
    assert view.text_input[0].value==''
    assert view.session_state['payload']['clarification_context']['original_question']=='第二个问题'
    assert 'clarification_context' not in sent[1] and 'clarification_answer' not in sent[1]


def test_mode_switch_clears_pending_and_sends_direct(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        body=kwargs['json']; sent.append(body)
        payload=({'status':'needs_clarification','clarification_question':'哪段时间？',
                  'clarification_context':{'original_question':body['question']}}
                 if body['mode']=='clarify' else {'status':'success','result':[]})
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    view.text_area[0].set_value('最近销售额').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert len(sent)==1 and len(view.text_input)==1
    next(x for x in view.toggle if x.label=='自动判断是否澄清').set_value(False).run()
    assert len(view.text_input)==0 and len(sent)==1
    view.text_area[0].set_value('累计有效订单销售额').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert not view.exception
    assert sent[1]=={'question':'累计有效订单销售额','mode':'direct'}


def test_invalid_output_is_visible_without_automatic_retry(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        sent.append(kwargs['json'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':'invalid_output'})
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    view.text_area[0].set_value('上个月销售额').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert not view.exception and len(sent)==1
    assert any('未通过校验，未执行查询' in x.value for x in view.warning)
    assert not view.dataframe


def test_empty_clarification_answer_does_not_send_request(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        sent.append(kwargs['json'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':'needs_clarification',
            'clarification_question':'哪段时间？','clarification_context':{'original_question':'最近销售额'}})
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    view.text_area[0].set_value('最近销售额').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    next(x for x in view.button if x.label=='继续分析').click().run(timeout=30)
    assert not view.exception and len(sent)==1
    assert any('请填写澄清回答' in x.value for x in view.warning)


def test_failed_followup_retains_answer_and_context(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        sent.append(kwargs)
        payload=({'status':'needs_clarification','clarification_question':'哪个城市？',
                  'clarification_context':{'original_question':'某个城市的用户数','clarification_question':'哪个城市？'}}
                 if len(sent)==1 else {'status':'invalid_output','error_code':'gate_validation_failed'})
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    view.text_area[0].set_value('某个城市的用户数').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    view.text_input[0].set_value('北京市').run()
    next(x for x in view.button if x.label=='继续分析').click().run(timeout=30)
    assert not view.exception and len(sent)==2
    assert view.text_input[0].value=='北京市'
    assert view.session_state['pending_context']['original_question']=='某个城市的用户数'
    assert sent[1]['headers']['X-Parent-Request-ID']==sent[0]['headers']['X-Request-ID']
    assert sent[1]['headers']['X-Request-ID']!=sent[0]['headers']['X-Request-ID']
    assert not view.dataframe and any('系统澄清' in x.value for x in view.warning)


def test_example_updates_submitted_question_and_response_id(monkeypatch):
    import requests
    sent=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    def post(*args,**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':'success','result':[{'n':1}],
                               'request_id':kwargs['headers']['X-Request-ID']})
    monkeypatch.setattr(requests,'post',post)
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    example='各城市有效订单数量是多少？'
    next(x for x in view.button if x.label==example).click().run()
    assert view.text_area[0].value==example and not sent
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    view.run()
    assert not view.exception and len(sent)==1 and sent[0]['json']['question']==example
    assert view.session_state['payload']['request_id']==sent[0]['headers']['X-Request-ID']
    assert view.metric[0].value=='查询已执行'


def test_wrong_response_id_never_displays_result(monkeypatch):
    import requests
    monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(ok=True))
    monkeypatch.setattr(requests,'post',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,
        json=lambda:{'status':'success','request_id':'wrong-request','result':[{'n':999}]}))
    view=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/app.py')).run(timeout=30)
    view.text_area[0].set_value('用户数').run()
    next(x for x in view.button if x.label=='开始分析').click().run(timeout=30)
    assert not view.exception and not view.dataframe and view.error
