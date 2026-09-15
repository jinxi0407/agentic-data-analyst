from types import SimpleNamespace

import pytest
import requests

from app.tools import qwen


class Response(dict):
    __getattr__ = dict.__getitem__


@pytest.mark.parametrize('timeout', [None, (5,30)])
def test_timeout_is_opt_in_and_sql_defaults_unchanged(monkeypatch, timeout):
    calls = []
    def call(**kwargs):
        calls.append(kwargs)
        return Response(status_code=200,usage={'input_tokens':2,'output_tokens':1},
                        output={'choices':[{'message':{'content':'OK'}}]})
    monkeypatch.setattr(qwen,'_require_dashscope',lambda:SimpleNamespace(Generation=SimpleNamespace(call=call)))
    messages = [{'role':'user','content':'Only OK'}]
    kwargs = {} if timeout is None else {'request_timeout':timeout}
    with qwen.capture_usage() as usage:
        assert qwen.generate_text(messages,temperature=.05,**kwargs) == 'OK'
    assert calls[0]['messages'] is messages
    assert calls[0]['temperature'] == .05
    assert 'max_tokens' not in calls[0] and 'stream' not in calls[0]
    if timeout is None:
        assert set(calls[0]) == {'model','messages','temperature','result_format'}
    else:
        assert calls[0]['request_timeout'] == timeout
    assert len(calls) == len(usage) == 1


def test_read_timeout_does_not_add_wrapper_retry(monkeypatch):
    calls = []
    def call(**kwargs):
        calls.append(kwargs)
        raise requests.ReadTimeout('test only')
    monkeypatch.setattr(qwen,'_require_dashscope',lambda:SimpleNamespace(Generation=SimpleNamespace(call=call)))
    with qwen.capture_usage() as usage, pytest.raises(requests.ReadTimeout):
        qwen.generate_text([],request_timeout=(5,30))
    assert len(calls) == len(usage) == 1
    assert usage[0]['status'] == 'transport_error'


@pytest.mark.parametrize('error,expected', [(requests.ConnectionError,2),(requests.ReadTimeout,1)])
def test_existing_sdk_transport_retry_bound(error,expected):
    from dashscope.api_entities.http_request import _send_with_retry
    calls = []
    def send():
        calls.append(1)
        raise error('test only')
    with pytest.raises(error):
        _send_with_retry(send)
    assert len(calls) == expected


def test_gate_transport_error_is_not_format_retry(monkeypatch):
    from app.agent import scoped_clarification as gate
    calls = []
    monkeypatch.setattr(gate,'schema_context',lambda:'schema')
    monkeypatch.setattr(gate,'entity_context',lambda:'entities')
    def fail(*args,**kwargs):
        calls.append(kwargs)
        raise requests.ReadTimeout('test only')
    monkeypatch.setattr(gate,'generate_text',fail)
    assert gate.run_interactive('最近30天销售额是多少？')['status'] == 'system_error'
    assert len(calls) == 1


def test_development_runner_stays_serial():
    from eval.conservative_gate_experiment import WORKERS, PREFIX
    assert WORKERS == 1
    assert PREFIX.name not in ('conservative_gate_dev_round1','conservative_gate_dev_round2')
