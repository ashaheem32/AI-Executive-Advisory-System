import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def password_matches(password, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return secrets.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@contextmanager
def connect(settings):
    con = sqlite3.connect(settings.db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def initialize(settings):
    settings.validate()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with connect(settings) as con:
        con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','standard')),
          password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
          access TEXT NOT NULL CHECK(access IN ('public','confidential')),
          sha256 TEXT NOT NULL, text TEXT NOT NULL, created_by INTEGER REFERENCES users(id),
          created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
          location TEXT NOT NULL, text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, document_id TEXT UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
          status TEXT NOT NULL CHECK(status IN ('pending','processing','completed','failed')),
          attempts INTEGER NOT NULL DEFAULT 0, summary TEXT, error TEXT,
          created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, user_id INTEGER, event TEXT NOT NULL,
          target TEXT, detail TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
        CREATE INDEX IF NOT EXISTS audit_time ON audit(created_at);
        """)
        defaults = [("admin", "Mohammed", "admin", "AdminDemo!2026"),
                    ("user", "Shaheem", "standard", "UserDemo!2026")]
        for username, name, role, demo_password in defaults:
            if not con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                key = "ADMIN_PASSWORD" if role == "admin" else "USER_PASSWORD"
                password = os.getenv(key, demo_password if settings.demo else "")
                con.execute("INSERT INTO users(username,name,role,password_hash) VALUES (?,?,?,?)",
                            (username, name, role, password_hash(password)))
            elif not settings.demo:
                existing = con.execute("SELECT password_hash FROM users WHERE username=?", (username,)).fetchone()
                if password_matches(demo_password, existing["password_hash"]):
                    key = "ADMIN_PASSWORD" if role == "admin" else "USER_PASSWORD"
                    con.execute("UPDATE users SET password_hash=? WHERE username=?", (password_hash(os.environ[key]), username))
                    con.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (username,))
        # Interrupted jobs are durable and retried on restart.
        con.execute("UPDATE jobs SET status='pending' WHERE status='processing'")
    os.chmod(settings.db_path, 0o600)


def audit(settings, user_id, event, target="", detail=""):
    with connect(settings) as con:
        con.execute("INSERT INTO audit(user_id,event,target,detail,created_at) VALUES (?,?,?,?,?)",
                    (user_id, event, target, detail[:250], time.time()))


def visible_document(settings, document_id, role):
    with connect(settings) as con:
        row = con.execute("SELECT * FROM documents WHERE id=? AND (access='public' OR ?='admin')",
                          (document_id, role)).fetchone()
        return dict(row) if row else None
