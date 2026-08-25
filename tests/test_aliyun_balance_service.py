import importlib

import pytest


def test_balance_amount_removes_thousands_separator():
    module = importlib.import_module("app.services.aliyun_balance_service")
    assert module._normalize_amount("50,062.80") == "50062.80"
    assert module._normalize_amount("500.00") == "500.00"


def test_balance_service_requires_credentials(monkeypatch):
    module = importlib.import_module("app.services.aliyun_balance_service")
    monkeypatch.setattr(module.config, "ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    monkeypatch.setattr(module.config, "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    service = module.AliyunBalanceService()
    with pytest.raises(ValueError, match="AK/SK"):
        service.query()
