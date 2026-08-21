import importlib

import pytest


def test_balance_service_requires_credentials(monkeypatch):
    module = importlib.import_module("app.services.aliyun_balance_service")
    monkeypatch.setattr(module.config, "ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    monkeypatch.setattr(module.config, "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    service = module.AliyunBalanceService()
    with pytest.raises(ValueError, match="AK/SK"):
        service.query()
