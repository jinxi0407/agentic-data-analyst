from datetime import date
from types import SimpleNamespace

import pytest
import requests

from eval import conservative_gate_experiment as runner


@pytest.mark.parametrize('off,on,completed,expected', [
    (True,True,True,'off_correct_on_correct'),
    (True,False,True,'off_correct_on_wrong'),
    (True,False,False,'off_correct_on_incomplete'),
    (False,True,True,'off_wrong_on_correct'),
    (False,False,False,'off_wrong_on_wrong_or_incomplete'),
    (False,False,True,'off_wrong_on_wrong_or_incomplete'),
])
def test_pairing_keeps_incomplete_distinct(off,on,completed,expected):
    assert runner.paired_label({'correct':off},{'correct':on,'first_turn_completed':completed}) == expected


@pytest.mark.parametrize('kind', ['timeout','rate_limit'])
def test_failure_observer_preserves_type_without_payload(monkeypatch,kind):
    def call(**kwargs):
        if kind == 'timeout':
            raise requests.ReadTimeout('private details must not be copied')
        return SimpleNamespace(status_code=429,get=lambda key:'Throttling')
    sdk = SimpleNamespace(Generation=SimpleNamespace(call=call))
    monkeypatch.setattr(runner.qwen,'_require_dashscope',lambda:sdk)
    def measured(question,reference,mode):
        assert question == 'public question' and mode == 'on'
        try:
            sdk.Generation.call(response_format={'type':'json_object'})
        except requests.ReadTimeout:
            pass
        return {'state':'complete','payload':{'status':'system_error'},'usage':[],'elapsed_s':1}
    monkeypatch.setattr(runner.original,'measured_call',measured)
    result = runner.measured_on('public question',date(2026,9,12))
    assert len(result['failures']) == 1
    assert result['failures'][0]['stage'] == 'gate'
    assert result['failures'][0]['error_type'] == ('ReadTimeout' if kind=='timeout' else 'api_error')
    assert 'private details' not in str(result)
