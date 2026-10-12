import pytest
from app import create_app


@pytest.fixture()
def client(tmp_path):
    users_path = tmp_path / "users.json"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-only",
        "USERS_FILE": str(users_path),
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    })
    with app.test_client() as test_client:
        yield test_client


def register_user(client, email="test@example.com", password="Senha-Super-Segura-123!"):
    return client.post("/register", data={
        "name": "Usuário de Teste",
        "email": email,
        "password": password,
        "confirm_password": password,
    })


def test_login_page_has_native_login_and_registration(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"name=\"email\"" in response.data
    assert b"Criar uma conta" in response.data
    assert b"accounts.google.com" not in response.data
    assert b"Calculadora de IMC" in response.data
    assert b"SECUREOPS LAB" not in response.data
    assert "Sua senha é armazenada como hash seguro".encode() not in response.data


def test_dashboard_requires_authentication(client):
    response = client.get("/dashboard")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_registration_redirects_to_login_without_authenticating(client):
    response = register_user(client)
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 302 and "/login" in dashboard.headers["Location"]
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "Conta criada com sucesso".encode() in login_page.data


def test_duplicate_email_is_rejected_case_insensitively(client):
    register_user(client)
    client.post("/logout")
    response = register_user(client, email="TEST@example.com")
    assert response.status_code == 409


def test_registration_rejects_short_password(client):
    response = client.post("/register", data={
        "name": "Usuário", "email": "user@example.com",
        "password": "curta", "confirm_password": "curta",
    })
    assert response.status_code == 400
    assert b"12 e 128 caracteres" in response.data


@pytest.mark.parametrize("password", [
    "senha-sem-maiuscula-123!", "SENHA-SEM-MINUSCULA-123!",
    "Senha-Sem-Numero!", "SenhaSemSimbolo123",
])
def test_registration_requires_password_complexity(client, password):
    response = client.post("/register", data={
        "name": "Usuário", "email": "complex@example.com",
        "password": password, "confirm_password": password,
    })
    assert response.status_code == 400
    assert b"senha deve conter" in response.data.lower()


def test_login_with_valid_credentials(client):
    register_user(client)
    client.post("/logout")
    response = client.post("/login", data={
        "email": "TEST@example.com", "password": "Senha-Super-Segura-123!",
    })
    assert response.status_code == 302 and "/dashboard" in response.headers["Location"]
    assert client.get("/dashboard").status_code == 200


def test_login_rejects_invalid_password(client):
    register_user(client)
    client.post("/logout")
    response = client.post("/login", data={"email": "test@example.com", "password": "senha-errada"})
    assert response.status_code == 401
    assert client.get("/dashboard").status_code == 302


def test_logout_clears_session(client):
    register_user(client)
    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_calculation_requires_login(client):
    response = client.post("/calculate", data={"weight": "70", "height": "1.75"})
    assert response.status_code == 302


def test_security_headers(client):
    response = client.get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers


def test_user_file_stores_password_hash_not_plaintext(client, tmp_path):
    register_user(client)
    import json
    users = json.loads((tmp_path / "users.json").read_text(encoding="utf-8"))
    assert len(users) == 1
    assert users[0]["email"] == "test@example.com"
    assert users[0]["password_hash"] != "Senha-Super-Segura-123!"
    assert "Senha-Super-Segura-123!" not in (tmp_path / "users.json").read_text(encoding="utf-8")


def test_accounts_persist_after_app_recreation(tmp_path):
    users_path = tmp_path / "persistent-users.json"
    config = {
        "TESTING": True, "SECRET_KEY": "test-secret-key-only",
        "USERS_FILE": str(users_path), "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    }
    first_app = create_app(config)
    with first_app.test_client() as client:
        register_user(client, email="persist@example.com")
    second_app = create_app(config)
    with second_app.test_client() as client:
        response = client.post("/login", data={
            "email": "persist@example.com", "password": "Senha-Super-Segura-123!",
        })
        assert response.status_code == 302
        assert "/dashboard" in response.headers["Location"]
