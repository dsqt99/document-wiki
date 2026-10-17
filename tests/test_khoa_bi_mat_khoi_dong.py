"""Kiểm thử chốt chặn khoá bí mật lúc khởi động (app/main.py::_check_secrets_or_fail).

SECRET_KEY và MCP_TOKEN_PEPPER còn trống hoặc giá trị mẫu "change-me" thì ứng dụng từ chối khởi động,
trừ khi APP_ENV=dev (chỉ cảnh báo).
"""

import pytest

from app.config import settings
from app.main import _check_secrets_or_fail


def _dat(monkeypatch, secret_key, pepper, app_env):
    monkeypatch.setattr(settings, "secret_key", secret_key)
    monkeypatch.setattr(settings, "mcp_token_pepper", pepper)
    monkeypatch.setattr(settings, "app_env", app_env)


def test_tu_choi_khi_secret_key_con_gia_tri_mau(monkeypatch):
    _dat(monkeypatch, "change-me-to-a-random-secret-string", "p" * 32, "prod")
    with pytest.raises(RuntimeError) as err:
        _check_secrets_or_fail()
    assert "SECRET_KEY" in str(err.value)
    assert "MCP_TOKEN_PEPPER" not in str(err.value)


def test_tu_choi_khi_pepper_trong(monkeypatch):
    _dat(monkeypatch, "s" * 32, "   ", "prod")
    with pytest.raises(RuntimeError) as err:
        _check_secrets_or_fail()
    assert "MCP_TOKEN_PEPPER" in str(err.value)


def test_tu_choi_moi_gia_tri_bat_dau_bang_change_me(monkeypatch):
    _dat(monkeypatch, "change-me-khac", "change-me-nua", "production")
    with pytest.raises(RuntimeError) as err:
        _check_secrets_or_fail()
    assert "SECRET_KEY, MCP_TOKEN_PEPPER" in str(err.value)


def test_app_env_dev_chi_canh_bao(monkeypatch, caplog):
    _dat(monkeypatch, "change-me-to-a-random-secret-string", "change-me-to-a-random-pepper", "dev")
    with caplog.at_level("WARNING"):
        _check_secrets_or_fail()  # không raise
    assert any("APP_ENV=dev" in rec.getMessage() for rec in caplog.records)


def test_hop_le_khong_lam_gi(monkeypatch):
    _dat(monkeypatch, "s" * 32, "p" * 32, "prod")
    _check_secrets_or_fail()
