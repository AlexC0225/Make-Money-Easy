def test_automation_config_defaults_and_can_be_updated(client):
    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "auto-user",
            "email": "auto@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )
    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    get_response = client.get(f"/api/v1/strategies/automation/{user_id}")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["enabled"] is True
    assert get_payload["strategy_name"] == "connors_rsi2_long"
    assert get_payload["position_sizing_mode"] == "fixed_shares"
    assert get_payload["buy_quantity"] == 1000
    assert get_payload["cash_allocation_pct"] == 10.0

    update_response = client.put(
        f"/api/v1/strategies/automation/{user_id}",
        json={
            "enabled": False,
            "strategy_name": "hybrid_tw_strategy",
            "position_sizing_mode": "cash_percent",
            "buy_quantity": 2000,
            "cash_allocation_pct": 25,
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["enabled"] is False
    assert update_payload["strategy_name"] == "hybrid_tw_strategy"
    assert update_payload["position_sizing_mode"] == "cash_percent"
    assert update_payload["buy_quantity"] == 2000
    assert update_payload["cash_allocation_pct"] == 25.0
