def test_singleton_user_requires_setup_when_database_empty(client):
    response = client.get("/api/v1/users/singleton")

    assert response.status_code == 200
    assert response.json() == {
        "user": None,
        "active_user_id": None,
        "requires_setup": True,
    }


def test_user_login_with_email(client):
    create_response = client.post(
        "/api/v1/users",
        json={
            "username": "alex",
            "email": "alex@example.com",
            "initial_cash": 1_000_000,
        },
    )
    assert create_response.status_code == 201

    login_response = client.post(
        "/api/v1/users/login",
        json={
            "login": "alex@example.com",
        },
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["active_user_id"] == payload["user"]["id"]
    assert payload["user"]["email"] == "alex@example.com"


def test_user_login_rejects_unknown_user(client):
    create_response = client.post(
        "/api/v1/users",
        json={
            "username": "mike",
            "email": "mike@example.com",
            "initial_cash": 1_000_000,
        },
    )
    assert create_response.status_code == 201

    login_response = client.post(
        "/api/v1/users/login",
        json={
            "login": "nobody@example.com",
        },
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "User not found."


def test_create_user_rejects_second_workspace_user(client):
    first_response = client.post(
        "/api/v1/users",
        json={
            "username": "alex",
            "email": "alex@example.com",
            "initial_cash": 1_000_000,
        },
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/users",
        json={
            "username": "mike",
            "email": "mike@example.com",
            "initial_cash": 500_000,
        },
    )

    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Only one workspace user is supported."


def test_bootstrap_portfolio_reuses_singleton_user_when_user_id_missing(client):
    first_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "alex",
            "email": "alex@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 900_000,
            "positions": [],
        },
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()

    second_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "alex-updated",
            "email": "alex-updated@example.com",
            "initial_cash": 2_000_000,
            "available_cash": 1_500_000,
            "positions": [],
        },
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()

    assert second_payload["user_id"] == first_payload["user_id"]
    assert second_payload["username"] == "alex-updated"
    assert second_payload["email"] == "alex-updated@example.com"
    assert second_payload["initial_cash"] == 2_000_000
    assert second_payload["available_cash"] == 1_500_000

    singleton_response = client.get("/api/v1/users/singleton")
    assert singleton_response.status_code == 200
    singleton_payload = singleton_response.json()
    assert singleton_payload["requires_setup"] is False
    assert singleton_payload["active_user_id"] == first_payload["user_id"]
    assert singleton_payload["user"]["username"] == "alex-updated"
    assert singleton_payload["user"]["email"] == "alex-updated@example.com"
