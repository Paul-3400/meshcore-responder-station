"""
Authentifizierung fuer die MeshCore Responder-Station.
Login-Verwaltung, Passwort-Hashing (bcrypt), Session-Schutz.
Erstellt von Paul (Brain Gym) mit Hilfe von Claude (Anthropic, 2026).
Repo: https://github.com/Paul-3400/meshcore-responder-station
Version: 2.3
"""
import os
import bcrypt
from functools import wraps
from flask import session, redirect, url_for

# ============================================================
# KONFIGURATION
# ============================================================
AUTH_CONF_PATH = "/home/paul-rppi/meshcore-responder/auth.conf"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
SESSION_TIMEOUT = 90 * 60  # 90 Minuten in Sekunden

# ============================================================
# AUTH.CONF LESEN / SCHREIBEN
# ============================================================
def read_auth_conf():
    """Liest auth.conf und gibt Dictionary zurueck."""
    config = {
        "username": DEFAULT_USERNAME,
        "password_hash": "",
        "first_login": "true"
    }
    if not os.path.exists(AUTH_CONF_PATH):
        return config
    try:
        with open(AUTH_CONF_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or line.startswith('[') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    except Exception as e:
        print(f"  \u26a0 auth.conf Lesefehler: {e}")
    return config


def write_auth_conf(config):
    """Schreibt auth.conf."""
    try:
        with open(AUTH_CONF_PATH, 'w') as f:
            f.write("# Auth Configuration - MeshCore Responder-Station\n")
            f.write("# NICHT MANUELL BEARBEITEN\n\n")
            f.write("[auth]\n")
            f.write(f"username = {config['username']}\n")
            f.write(f"password_hash = {config['password_hash']}\n")
            f.write(f"first_login = {config['first_login']}\n")
        return True
    except Exception as e:
        print(f"  \u26a0 auth.conf Schreibfehler: {e}")
        return False

# ============================================================
# INITIALISIERUNG
# ============================================================
def init_auth():
    """Erstellt auth.conf mit Default-Werten falls nicht vorhanden."""
    if os.path.exists(AUTH_CONF_PATH):
        print(f"  \u2705 auth.conf vorhanden")
        return
    print(f"  \U0001f195 Erstelle auth.conf mit Default-Passwort...")
    hashed = hash_password(DEFAULT_PASSWORD)
    config = {
        "username": DEFAULT_USERNAME,
        "password_hash": hashed,
        "first_login": "true"
    }
    write_auth_conf(config)
    print(f"  \u2705 auth.conf angelegt (Default: admin/admin)")

# ============================================================
# PASSWORT-FUNKTIONEN
# ============================================================
def hash_password(password):
    """Hasht ein Passwort mit bcrypt."""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')


def check_password(password, stored_hash):
    """Prueft Passwort gegen gespeicherten Hash."""
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            stored_hash.encode('utf-8')
        )
    except Exception:
        return False


def verify_login(username, password):
    """Prueft Login-Credentials. Gibt (success, is_first_login) zurueck."""
    config = read_auth_conf()
    if username != config["username"]:
        return False, False
    if not check_password(password, config["password_hash"]):
        return False, False
    is_first = config.get("first_login", "false") == "true"
    return True, is_first


def change_password(new_password):
    """Speichert neues Passwort und setzt first_login auf false."""
    config = read_auth_conf()
    config["password_hash"] = hash_password(new_password)
    config["first_login"] = "false"
    return write_auth_conf(config)


def is_first_login():
    """Gibt True zurueck wenn noch Default-PW aktiv."""
    config = read_auth_conf()
    return config.get("first_login", "false") == "true"


def get_username():
    """Gibt aktuellen Username zurueck."""
    config = read_auth_conf()
    return config["username"]

# ============================================================
# FLASK SESSION-SCHUTZ (Decorator)
# ============================================================
def login_required(f):
    """Decorator: Leitet auf /login um wenn nicht eingeloggt."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
