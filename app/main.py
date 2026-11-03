import hashlib
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from .config import ROOT, Settings
from .db import initialize, connect, password_matches, password_hash, audit, visible_document
from .ingest import ingest, run_job, ProcessingError
from .advisors import respond


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        initialize(settings)
        app.state.dummy_password = password_hash("invalid-user-placeholder")
        if settings.demo:
            seeds = [("finance_Q2.txt", "finance", "public"), ("finance_Q3.txt", "finance", "public"),
                     ("employee_handbook.txt", "hr", "public"), ("remote_addendum.txt", "hr", "public"),
                     ("executive_compensation.txt", "hr", "confidential"), ("company_overview.txt", "general", "public")]
            with connect(settings) as con:
                admin_id = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"]
            for filename, category, access in seeds:
                path = ROOT / "sample_documents" / filename
                if path.exists():
                    ingest(settings, path.read_bytes(), filename, category, access, admin_id)
        with connect(settings) as con:
            pending = con.execute("SELECT document_id FROM jobs WHERE status='pending'").fetchall()
        for job in pending:
            run_job(settings, job["document_id"])
        yield

    app = FastAPI(title="Northstar Executive Advisory", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        return JSONResponse({"detail": "The database is temporarily unavailable. Please try again."}, status_code=503)

    @app.middleware("http")
    async def headers_and_origin(request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and origin:
            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme != request.url.scheme:
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        # Bound JSON requests before framework parsing. Raw uploads have their own streaming cap.
        if request.url.path in ("/api/login", "/api/ask"):
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body) > 16_384:
                    return JSONResponse({"detail": "Request is too large."}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store", "X-Frame-Options": "DENY",
        })
        if settings.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def user(request: Request):
        token = request.cookies.get("northstar_session", "")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with connect(settings) as con:
            row = con.execute("SELECT u.id,u.username,u.name,u.role,s.csrf FROM sessions s JOIN users u ON s.user_id=u.id "
                              "WHERE s.token_hash=? AND s.expires>?", (digest, time.time())).fetchone()
        if not row:
            raise HTTPException(401, "Sign in to continue.")
        if request.method not in ("GET", "HEAD", "OPTIONS") and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), row["csrf"]):
            audit(settings, row["id"], "csrf_denied", detail="Missing or invalid CSRF token")
            raise HTTPException(403, "Invalid request token. Refresh and try again.")
        return dict(row)

    def admin(current=Depends(user)):
        if current["role"] != "admin":
            audit(settings, current["id"], "admin_denied", detail="Administrator action blocked")
            raise HTTPException(403, "Administrator access is required.")
        return current

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app/static/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")

    @app.get("/healthz")
    def health():
        try:
            with connect(settings) as con:
                con.execute("SELECT 1").fetchone()
            return {"status": "ok"}
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.get("/api/config")
    def public_config():
        return {"demo": settings.demo}

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        peer = request.client.host if request.client else "unknown"
        bucket = hashlib.sha256(peer.encode()).hexdigest()[:24]
        with connect(settings) as con:
            count = con.execute("SELECT count(*) FROM audit WHERE event='login_failed' AND target=? AND created_at>?", (bucket, time.time() - 300)).fetchone()[0]
            row = con.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
        if count >= 8:
            raise HTTPException(429, "Too many failed attempts. Try again in five minutes.")
        valid = password_matches(body.password, row["password_hash"] if row else app.state.dummy_password)
        if not row or not valid:
            audit(settings, None, "login_failed", bucket, "Invalid credentials")
            raise HTTPException(401, "Incorrect username or password.")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with connect(settings) as con:
            con.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            old = request.cookies.get("northstar_session", "")
            con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(old.encode()).hexdigest(),))
            con.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, time.time() + settings.session_seconds))
        response.set_cookie("northstar_session", token, httponly=True, secure=settings.secure_cookie, samesite="strict", max_age=settings.session_seconds, path="/")
        audit(settings, row["id"], "login_success", detail=row["role"])
        return {"id": row["id"], "username": row["username"], "name": row["name"], "role": row["role"], "csrf": csrf}

    @app.get("/api/me")
    def me(current=Depends(user)):
        return {**current, "demo": settings.demo, "ai_enabled": bool(settings.api_key), "model": settings.model if settings.api_key else None}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, current=Depends(user)):
        token = request.cookies.get("northstar_session", "")
        with connect(settings) as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie("northstar_session", path="/")
        return {"ok": True}

    @app.get("/api/documents")
    def documents(current=Depends(user)):
        with connect(settings) as con:
            rows = con.execute("SELECT d.id,d.name,d.category,d.access,d.created_at,j.status,j.summary,j.error,j.attempts,"
                               "(SELECT count(*) FROM chunks WHERE document_id=d.id) AS chunks "
                               "FROM documents d LEFT JOIN jobs j ON j.document_id=d.id "
                               "WHERE d.access='public' OR ?='admin' ORDER BY d.created_at DESC", (current["role"],)).fetchall()
        return [dict(row) for row in rows]

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str, current=Depends(user)):
        doc = visible_document(settings, doc_id, current["role"])
        if not doc:
            audit(settings, current["id"], "document_denied", doc_id[:64], "Not found or not authorized")
            raise HTTPException(404, "Document not found.")
        with connect(settings) as con:
            rows = con.execute("SELECT id,location,text FROM chunks WHERE document_id=?", (doc_id,)).fetchall()
        return {"id": doc["id"], "name": doc["name"], "category": doc["category"], "access": doc["access"], "text": doc["text"], "chunks": [dict(r) for r in rows]}

    @app.post("/api/documents", status_code=201)
    async def upload(request: Request, background: BackgroundTasks, name: str, category: str = "general", access: str = "public", current=Depends(admin)):
        if category not in ("general", "finance", "hr") or access not in ("public", "confidential"):
            raise HTTPException(422, "Choose a valid category and access level.")
        if not name or len(name) > 150 or Path(name).name != name or "\\" in name or any(ord(c) < 32 for c in name):
            raise HTTPException(422, "Choose a simple filename of at most 150 characters.")
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > settings.max_upload:
                raise HTTPException(413, "Maximum upload size is 5 MB.")
        try:
            # Parsing is blocking; use the framework thread pool so health/login remain responsive.
            from starlette.concurrency import run_in_threadpool
            doc_id, created = await run_in_threadpool(ingest, settings, bytes(data), name, category, access, current["id"])
        except ProcessingError as exc:
            audit(settings, current["id"], "processing_failed", detail="Rejected unreadable or unsupported upload")
            raise HTTPException(422, str(exc))
        background.add_task(run_job, settings, doc_id)
        return {"id": doc_id, "created": created, "message": "Document uploaded; summary automation queued." if created else "This document is already indexed."}

    @app.post("/api/documents/{doc_id}/retry")
    def retry(doc_id: str, background: BackgroundTasks, current=Depends(admin)):
        with connect(settings) as con:
            job = con.execute("SELECT status FROM jobs WHERE document_id=?", (doc_id,)).fetchone()
            if not job:
                raise HTTPException(404, "Job not found.")
            if job["status"] != "failed":
                raise HTTPException(409, "Only failed jobs can be retried.")
            con.execute("UPDATE jobs SET status='pending',updated_at=? WHERE document_id=? AND status='failed'", (time.time(), doc_id))
        background.add_task(run_job, settings, doc_id)
        audit(settings, current["id"], "automation_retry", doc_id)
        return {"ok": True}

    @app.post("/api/ask")
    def ask(body: Question, current=Depends(user)):
        if len(body.question.strip()) < 3:
            raise HTTPException(422, "Please enter a question.")
        with connect(settings) as con:
            count = con.execute("SELECT count(*) FROM audit WHERE user_id=? AND event='ask_requested' AND created_at>?", (current["id"], time.time() - 60)).fetchone()[0]
        if count >= 30:
            raise HTTPException(429, "Please wait a minute before asking more questions.")
        audit(settings, current["id"], "ask_requested", detail=f"{len(body.question)} characters")
        return respond(settings, body.question.strip(), current)

    @app.get("/api/audit")
    def audit_log(current=Depends(admin)):
        with connect(settings) as con:
            rows = con.execute("SELECT a.id,a.event,a.target,a.detail,a.created_at,COALESCE(u.username,'system') AS actor "
                               "FROM audit a LEFT JOIN users u ON a.user_id=u.id ORDER BY a.id DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    return app


app = create_app()
