def test_signup_login_me(api_client):
    r = api_client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "teacher@test.local"

    r = api_client.post(
        "/api/v1/auth/login", json={"email": "teacher@test.local", "password": "test-password-123"}
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password_rejected(api_client):
    r = api_client.post("/api/v1/auth/login", json={"email": "teacher@test.local", "password": "wrong"})
    assert r.status_code == 401


def test_signup_duplicate_email_rejected(api_client):
    r = api_client.post(
        "/api/v1/auth/signup",
        json={"email": "teacher@test.local", "password": "another-password", "name": "Someone Else"},
    )
    assert r.status_code == 409


def test_protected_endpoint_without_token_rejected(api_client):
    api_client.headers.pop("Authorization")
    r = api_client.get("/api/v1/exams")
    assert r.status_code in (401, 403)
