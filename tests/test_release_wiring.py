import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agent import scoped_clarification as scoped
from scripts import local_services as services


@pytest.mark.parametrize("endpoint", ["/api/query", "/api/scoped-query"])
def test_default_and_explicit_direct_never_call_gate(monkeypatch, endpoint):
    calls=[]
    monkeypatch.setattr(scoped,"decide",lambda *a,**k:pytest.fail("Direct mode invoked Gate"))
    monkeypatch.setattr(scoped,"run_interactive",lambda *a,**k:pytest.fail("Direct mode invoked interactive path"))
    monkeypatch.setattr(scoped,"direct",lambda q:calls.append(q) or {"status":"success","result":[]})
    client=TestClient(app)
    for body in [{"question":"注册人数"},{"question":"注册人数","mode":"direct"}]:
        assert client.post(endpoint,json=body).json()["status"]=="success"
    assert calls==["注册人数","注册人数"]


def test_explicit_mode_uses_frozen_scoped_entrypoint(monkeypatch):
    calls=[]
    monkeypatch.setattr(scoped,"run_interactive",lambda *args:calls.append(args) or {"status":"needs_clarification"})
    assert TestClient(app).post('/api/query',json={'question':'q','mode':'clarify'}).json()['status']=='needs_clarification'
    assert calls==[('q',None,None)]


def test_healthy_owned_runtime_is_reusable(monkeypatch,tmp_path):
    monkeypatch.setattr(services,'RUN',tmp_path)
    (tmp_path/'fastapi.pid').write_text('123')
    (tmp_path/'fastapi.json').write_text(json.dumps({'runtime_fingerprint':'current'}))
    monkeypatch.setattr(services,'owns',lambda *a:True)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(services,'urlopen',lambda *a,**k:Response())
    assert services.can_reuse('fastapi','current')
    assert not services.can_reuse('fastapi','changed')
    monkeypatch.setattr(services,'owns',lambda *a:False)
    assert not services.can_reuse('fastapi','current')


def test_unknown_port_is_not_killed(monkeypatch):
    import socket
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        monkeypatch.setattr(services.os,'kill',lambda *a:pytest.fail('Unknown process killed'))
        with pytest.raises(RuntimeError,match='occupied'):
            services.free_port(listener.getsockname()[1])
