import pytest

from app.core.config import DEV_JWT_SECRET, Settings
from app.main import cors_kwargs


def test_validate_for_prod_rejects_dev_secret():
    s = Settings(env="prod", jwt_secret=DEV_JWT_SECRET, use_mock_data=False, data_dir="/tmp/signal-data")
    with pytest.raises(RuntimeError, match="dev secret"):
        s.validate_for_prod()


def test_validate_for_prod_rejects_short_secret():
    s = Settings(env="prod", jwt_secret="s" * 31, use_mock_data=False, data_dir="/tmp/signal-data")
    with pytest.raises(RuntimeError, match="32 bytes"):
        s.validate_for_prod()


def test_validate_for_prod_rejects_mock_data():
    s = Settings(env="prod", jwt_secret="s" * 32, use_mock_data=True, data_dir="/tmp/signal-data")
    with pytest.raises(RuntimeError, match="mock data"):
        s.validate_for_prod()


def test_validate_for_prod_accepts_strong_secret_without_mocks():
    s = Settings(
        env="prod", jwt_secret="s" * 32, use_mock_data=False,
        redis_url="redis://localhost:6379/0",
        data_dir="/tmp/signal-data",
    )
    s.validate_for_prod()


def test_validate_for_prod_requires_redis():
    s = Settings(
        env="prod", jwt_secret="s" * 32, use_mock_data=False, redis_url=None,
        data_dir="/tmp/signal-data",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        s.validate_for_prod()


def test_validate_for_prod_requires_data_dir():
    s = Settings(
        env="prod", jwt_secret="s" * 32, use_mock_data=False,
        redis_url="redis://localhost:6379/0", data_dir=None,
    )
    with pytest.raises(RuntimeError, match="DATA_DIR"):
        s.validate_for_prod()


def test_validate_for_staging_requires_data_dir():
    s = Settings(env="staging", data_dir=None)
    with pytest.raises(RuntimeError, match="DATA_DIR"):
        s.validate_for_prod()


def test_validate_for_staging_accepts_data_dir_without_prod_secrets():
    s = Settings(env="staging", data_dir="/tmp/signal-data")
    s.validate_for_prod()


def test_dev_defaults_data_dir_to_repo_store():
    from pathlib import Path

    from app.core.data_dir import default_dev_data_dir

    s = Settings(env="dev", data_dir=None)
    s.validate_for_prod()
    assert s.data_dir == default_dev_data_dir()
    assert Path(s.data_dir).is_absolute()
    assert Path(s.data_dir).name == "store"
    assert Path(s.data_dir).parent.name == "data"


def test_settings_data_dir_reads_signal_data_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.data_dir == str(tmp_path.resolve())



def test_cors_credentials_only_with_explicit_origins():
    kw = cors_kwargs(Settings(cors_origins=["http://localhost:3000"]))
    assert kw["allow_credentials"] is True
    assert kw["allow_origins"] == ["http://localhost:3000"]
    assert kw["allow_methods"] == ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    assert kw["allow_headers"] == ["Authorization", "Content-Type", "X-API-Key"]
    wild = cors_kwargs(Settings(cors_origins=["*"]))
    assert wild["allow_credentials"] is False
    assert wild["allow_origins"] == ["*"]


def test_cors_origins_accept_comma_separated_env(monkeypatch):
    monkeypatch.setenv("SIGNAL_CORS_ORIGINS", "https://a.example,https://b.example")
    s = Settings()
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_validate_for_prod_rejects_serve_unapproved():
    s = Settings(
        env="prod", jwt_secret="s" * 32, use_mock_data=False, serve_unapproved=True,
        data_dir="/tmp/signal-data",
    )
    with pytest.raises(RuntimeError, match="SERVE_UNAPPROVED"):
        s.validate_for_prod()


def test_trusted_proxies_default_covers_localhost():
    from app.core.config import DEFAULT_TRUSTED_PROXIES
    from app.core.host import client_is_trusted

    s = Settings()
    assert "localhost" in s.trusted_proxies or any("127.0.0.0/8" in p for p in s.trusted_proxies)
    assert client_is_trusted("127.0.0.1", s.trusted_proxies)
    assert client_is_trusted("localhost", s.trusted_proxies)
    assert client_is_trusted("::1", s.trusted_proxies)
    assert not client_is_trusted("203.0.113.5", s.trusted_proxies)
    # Vercel (or any non-loopback) is not hardcoded; it comes from config.
    assert not any("vercel" in p.lower() for p in DEFAULT_TRUSTED_PROXIES)


def test_allow_unapproved_only_in_dev():
    assert Settings(env="dev", serve_unapproved=True).allow_unapproved() is True
    assert Settings(env="dev", serve_unapproved=False).allow_unapproved() is False
    assert Settings(env="prod", serve_unapproved=True, jwt_secret="s" * 32,
                    use_mock_data=False).allow_unapproved() is False


def test_location_kwargs_pass_store_root_not_a_store_child():
    from app.core.data_dir import location_kwargs

    def _store_only(symbol, timeframe, *, store_dir=None):
        return store_dir

    def _data_only(symbol, timeframe, *, data_dir=None):
        return data_dir

    def _both(symbol, timeframe, *, data_dir=None, store_dir=None):
        return data_dir, store_dir

    root = "/tmp/signal-store"
    assert location_kwargs(_store_only, root) == {"store_dir": root}
    assert location_kwargs(_data_only, root) == {"data_dir": root}
    assert location_kwargs(_both, root) == {"data_dir": root, "store_dir": root}
