from app.config import load_settings


def test_config_defaults_load():
    settings = load_settings()
    assert settings.mysql_host == "127.0.0.1"
    assert settings.mysql_port == 3307
    assert settings.api_port == 8002
