from app.services import billing_service


def test_settle_omni_video_charge_uses_multiplied_actual_tokens(monkeypatch):
    created_entries = []

    monkeypatch.setattr(
        billing_service.database,
        "has_ledger_entry",
        lambda user_id, entry_type, biz_type, biz_id: False,
    )
    monkeypatch.setattr(
        billing_service.database,
        "get_user_by_id",
        lambda user_id: {
            "id": user_id,
            "role_code": "external_user",
            "balance_cent": 10000,
            "pricing_multiplier": 1.5,
        },
    )
    monkeypatch.setattr(
        billing_service.database,
        "get_role_pricing_multiplier",
        lambda role_code: 1.0,
    )
    monkeypatch.setattr(
        billing_service.database,
        "resolve_model_pricing",
        lambda **kwargs: {
            "model_code": kwargs["model_code"],
            "currency_code": "CNY",
            "price_per_million_token_cent": 100000,
            "enabled": 1,
        },
    )
    monkeypatch.setattr(
        billing_service.database,
        "create_account_ledger_entry",
        lambda **kwargs: created_entries.append(kwargs),
    )

    billing_service.settle_omni_video_charge(
        {
            "task_id": "task-1",
            "user_id": 10,
            "model": "doubao-seedance-2-0-fast-260128",
            "token_usage": 1234,
        }
    )

    assert len(created_entries) == 1
    entry = created_entries[0]
    assert entry["tokens_raw"] == 1234
    assert entry["tokens_billed"] == 1851
    assert entry["amount_cent"] == 185
