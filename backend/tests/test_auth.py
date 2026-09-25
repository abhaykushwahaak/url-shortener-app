"""Authentication: registration, login, validation and token handling."""

from tests.conftest import TEST_PASSWORD, get_user, register


class TestRegister:
    def test_register_returns_token_and_user(self, client):
        body = register(client, "new@example.com")
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["email"] == "new@example.com"
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]

    def test_password_is_hashed_not_stored_plaintext(self, client, db):
        register(client, "hash@example.com")
        user = get_user(db, "hash@example.com")
        assert user is not None
        assert user.password_hash != TEST_PASSWORD
        # bcrypt hashes are prefixed with the algorithm and cost.
        assert user.password_hash.startswith("$2b$")

    def test_duplicate_email_is_rejected(self, client):
        register(client, "dupe@example.com")
        response = client.post(
            "/api/auth/register",
            json={"email": "dupe@example.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_email_is_case_insensitive(self, client):
        register(client, "Case@Example.com")
        response = client.post(
            "/api/auth/register",
            json={"email": "case@example.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 409

    def test_invalid_email_is_rejected(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": TEST_PASSWORD}
        )
        assert response.status_code == 422

    def test_short_password_is_rejected(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "short@example.com", "password": "abc"}
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_succeeds_with_correct_credentials(self, client):
        register(client, "login@example.com")
        response = client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_wrong_password_is_rejected(self, client):
        register(client, "wrong@example.com")
        response = client.post(
            "/api/auth/login",
            json={"email": "wrong@example.com", "password": "totally-wrong"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password"

    def test_unknown_email_is_rejected(self, client):
        response = client.post(
            "/api/auth/login",
            json={"email": "ghost@example.com", "password": TEST_PASSWORD},
        )
        assert response.status_code == 401
        # Identical message to the wrong-password case: no account enumeration.
        assert response.json()["detail"] == "Incorrect email or password"


class TestCurrentUser:
    def test_me_returns_the_authenticated_user(self, client, auth):
        response = client.get("/api/auth/me", headers=auth["headers"])
        assert response.status_code == 200
        assert response.json()["email"] == "owner@example.com"

    def test_me_without_token_is_401(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_with_garbage_token_is_401(self, client):
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert response.status_code == 401

    def test_token_signed_with_another_secret_is_401(self, client, auth):
        """Guards against the signature ever being skipped during verification."""
        import jwt

        forged = jwt.encode({"sub": auth["user"]["id"]}, "wrong-secret", algorithm="HS256")
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401