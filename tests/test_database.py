from app.tools import database


class DummyCursor:
    description = [("answer",)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return [{"answer": 42}]


class DummyConnection:
    def cursor(self):
        return DummyCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_fetch_all_uses_connection(monkeypatch):
    monkeypatch.setattr(database, "_connect", lambda user=None, password=None: DummyConnection())
    rows = database.fetch_all("SELECT 42 AS answer")
    assert rows == [{"answer": 42}]


def test_execute_agent_select(monkeypatch):
    monkeypatch.setattr(database, "_connect", lambda user=None, password=None: DummyConnection())
    rows = database.execute_agent_select("SELECT 42 AS answer")
    assert rows[0]["answer"] == 42
