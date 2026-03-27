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
