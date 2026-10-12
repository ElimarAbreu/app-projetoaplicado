import json
import os
import re
import secrets
import tempfile
import threading
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from filelock import FileLock, Timeout
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")


def login_required(view):
    """Verifica autorização no servidor, e não apenas na interface."""
    @wraps(view)
    def wrapped_view(**kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view


def classify_bmi(bmi):
    if bmi < 17: return "Muito abaixo do peso"
    if bmi < 18.5: return "Abaixo do peso"
    if bmi < 25: return "Peso normal"
    if bmi < 30: return "Acima do peso"
    if bmi < 35: return "Obesidade I"
    if bmi < 40: return "Obesidade II (severa)"
    return "Obesidade III (mórbida)"


def create_app(test_config=None):
    app = Flask(__name__)
    environment = os.getenv("APP_ENV", "development").lower()
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if environment == "production":
            raise RuntimeError("SECRET_KEY deve ser configurada em produção.")
        secret_key = secrets.token_hex(32)
    default_users_file = Path(app.instance_path) / "users.json"
    app.config.update(
        SECRET_KEY=secret_key,
        APP_ENV=environment,
        USERS_FILE=os.getenv("USERS_FILE", str(default_users_file)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(environment == "production"),
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        WTF_CSRF_ENABLED=True,
        RATELIMIT_ENABLED=True,
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    csrf.init_app(app)
    limiter.init_app(app)

    users_file = Path(app.config["USERS_FILE"]).expanduser().resolve()
    users_file.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(users_file) + ".lock", timeout=10)
    process_lock = threading.RLock()

    def read_users_unlocked():
        if not users_file.exists():
            return []
        try:
            with users_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            app.logger.error("Arquivo de usuários inválido; operação interrompida.")
            raise RuntimeError("O arquivo de usuários está inválido. Restaure um backup válido antes de continuar.") from exc
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise RuntimeError("Formato inválido no arquivo de usuários; operação interrompida.")
        return data

    def read_users():
        with process_lock, lock:
            return read_users_unlocked()

    def write_users_unlocked(users):
        # Gravação atômica evita deixar JSON parcialmente escrito se o processo falhar.
        fd, temporary_name = tempfile.mkstemp(prefix="users-", suffix=".tmp", dir=str(users_file.parent))
        try:
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(users, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, users_file)
            if os.name == "posix":
                os.chmod(users_file, 0o600)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def find_user_by_email(email):
        normalized = email.strip().lower()
        return next((user for user in read_users() if user.get("email", "").lower() == normalized), None)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if session.get("user_id") is not None else "login"))

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def login():
        if session.get("user_id") is not None:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            try:
                user = find_user_by_email(email)
            except (RuntimeError, Timeout):
                app.logger.exception("Não foi possível ler o arquivo de usuários.")
                flash("Não foi possível processar o login neste momento.", "error")
                return render_template("login.html", email=email), 503
            if not user or not check_password_hash(user.get("password_hash", ""), password):
                flash("E-mail ou senha inválidos.", "error")
                return render_template("login.html", email=email), 401
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["name"]
            session.permanent = True
            flash("Login realizado com sucesso.", "success")
            return redirect(url_for("dashboard"))
        return render_template("login.html", email="")

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def register():
        if session.get("user_id") is not None:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            name = " ".join(request.form.get("name", "").split())
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            errors = []
            if len(name) < 2 or len(name) > 80:
                errors.append("Informe um nome entre 2 e 80 caracteres.")
            if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                errors.append("Informe um endereço de e-mail válido.")
            if len(password) < 12 or len(password) > 128:
                errors.append("A senha deve ter entre 12 e 128 caracteres.")
            if not re.search(r"[a-z]", password):
                errors.append("A senha deve conter pelo menos uma letra minúscula.")
            if not re.search(r"[A-Z]", password):
                errors.append("A senha deve conter pelo menos uma letra maiúscula.")
            if not re.search(r"[0-9]", password):
                errors.append("A senha deve conter pelo menos um número.")
            if not re.search(r"[^A-Za-z0-9]", password):
                errors.append("A senha deve conter pelo menos um símbolo (por exemplo: @, # ou !).")
            if password != confirmation:
                errors.append("A confirmação de senha não corresponde.")
            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template("register.html", name=name, email=email), 400

            # O lock abrange a verificação e a gravação para reduzir corridas entre cadastros.
            try:
                with process_lock, lock:
                    users = read_users_unlocked()
                    if any(user.get("email", "").lower() == email for user in users):
                        flash("Não foi possível criar a conta com esses dados. Verifique se o e-mail já está cadastrado.", "error")
                        return render_template("register.html", name=name, email=email), 409
                    user = {
                        "id": str(uuid.uuid4()),
                        "name": name,
                        "email": email,
                        "password_hash": generate_password_hash(password),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    users.append(user)
                    write_users_unlocked(users)
            except (RuntimeError, Timeout, OSError):
                app.logger.exception("Não foi possível gravar o arquivo de usuários.")
                flash("Não foi possível criar a conta neste momento.", "error")
                return render_template("register.html", name=name, email=email), 503

            # Cadastro não autentica automaticamente: o usuário deve entrar pela tela de login.
            session.clear()
            flash("Conta criada com sucesso. Faça login para continuar.", "success")
            return redirect(url_for("login"))
        return render_template("register.html", name="", email="")

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", username=session.get("username", "usuário"), result=None)

    @app.post("/calculate")
    @login_required
    def calculate():
        try:
            weight = float(request.form.get("weight", "").strip().replace(",", "."))
            height = float(request.form.get("height", "").strip().replace(",", "."))
        except (ValueError, TypeError):
            flash("Informe peso e altura com valores numéricos válidos.", "error")
            return redirect(url_for("dashboard"))
        if not (0 < weight <= 500) or not (0 < height <= 3):
            flash("Use peso maior que 0 e até 500 kg e altura maior que 0 e até 3 m.", "error")
            return redirect(url_for("dashboard"))
        bmi = weight / (height ** 2)
        result = {"bmi": f"{bmi:.2f}".replace(".", ","), "classification": classify_bmi(bmi)}
        return render_template("dashboard.html", username=session.get("username", "usuário"), result=result)

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Você encerrou sua sessão.", "success")
        return redirect(url_for("login"))

    return app


app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
