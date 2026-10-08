"""Authentification et autorisations distinctes du dashboard, bridge et caméra."""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from api_access import load_environment

COOKIE = "sentinel_session"
TTL = 8 * 3600
ITERATIONS = 600_000


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt + ":" + digest


def install_security(app, base_dir):
    load_environment()
    names = ("PASSWORD_HASH", "SESSION_SECRET", "BRIDGE_KEY", "VISION_KEY")
    config = {name: os.environ.get("SENTINEL_" + name, "") for name in names}
    if any(len(value) < 32 for value in config.values()):
        raise RuntimeError("Sécurité non configurée : lancer setup_security.py, puis redémarrer l'API.")
    salt, digest = config["PASSWORD_HASH"].split(":")
    bytes.fromhex(salt)
    if len(digest) != 64 or config["BRIDGE_KEY"] == config["VISION_KEY"]:
        raise RuntimeError("Configuration de sécurité invalide.")
    attempts = defaultdict(deque)
    sessions = {}
    secure_cookie = os.environ.get("SENTINEL_COOKIE_SECURE", "false").lower() == "true"

    def signature(value):
        return hmac.new(config["SESSION_SECRET"].encode(), value.encode(), hashlib.sha256).hexdigest()

    def session_valid(request):
        token = request.cookies.get(COOKIE, "")
        value, separator, signed = token.rpartition(".")
        return bool(separator and hmac.compare_digest(signature(value).encode(), signed.encode())
                    and sessions.get(value, 0) > time.time())

    def same_origin(request):
        origin = request.headers.get("origin")
        if not origin:
            return False
        parsed = urlsplit(origin)
        return parsed.scheme == request.url.scheme and parsed.netloc == request.headers.get("host")

    def allowed(role, method, path):
        if role == "dashboard":
            return (method == "GET" and path in {
                "/api/v1/readings", "/api/v1/alerts", "/api/v1/frame",
                "/api/v1/device/state", "/api/v1/commands"}) or (method == "POST" and path == "/api/v1/commands")
        if role == "vision":
            return method == "POST" and path in {"/api/v1/frame", "/api/v1/alerts"}
        return (method, path) in {
            ("POST", "/api/v1/readings"), ("POST", "/api/v1/device/state"),
            ("GET", "/api/v1/commands/pending")
        } or (method == "POST" and path.startswith("/api/v1/commands/") and path.endswith("/result"))

    @app.middleware("http")
    async def protect(request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            role = None
            authorization = request.headers.get("authorization", "")
            if authorization.startswith("Bearer "):
                for candidate in ("bridge", "vision"):
                    if hmac.compare_digest(authorization[7:].encode(), config[candidate.upper() + "_KEY"].encode()):
                        role = candidate
            elif session_valid(request):
                role = "dashboard"
            if role is None:
                return JSONResponse({"detail": "Connexion requise."}, status_code=401)
            if not allowed(role, request.method, path):
                return JSONResponse({"detail": "Accès non autorisé pour ce compte."}, status_code=403)
            if role == "dashboard" and request.method != "GET" and not same_origin(request):
                return JSONResponse({"detail": "Origine refusée."}, status_code=403)
        elif path == "/" and not session_valid(request):
            return RedirectResponse("/auth/login", status_code=303)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/auth/login")
    def login_page():
        return FileResponse(base_dir / "login.html")

    @app.post("/auth/login")
    async def login(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "Origine refusée."}, status_code=403)
        now = time.time()
        for key in list(attempts):
            while attempts[key] and attempts[key][0] < now - 60:
                attempts[key].popleft()
            if not attempts[key]:
                del attempts[key]
        address = request.client.host
        if len(attempts[address]) >= 5:
            return JSONResponse({"detail": "Trop de tentatives. Réessayer dans une minute."}, status_code=429)
        attempts[address].append(now)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({"detail": "Requête trop volumineuse."}, status_code=413)
        try:
            import json
            password = json.loads(body).get("password", "")
            valid = isinstance(password, str) and hmac.compare_digest(password_hash(password, salt), config["PASSWORD_HASH"])
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            return JSONResponse({"detail": "Mot de passe incorrect."}, status_code=401)
        attempts.pop(address, None)
        for value in list(sessions):
            if sessions[value] <= now:
                sessions.pop(value, None)
        if len(sessions) >= 100:
            return JSONResponse({"detail": "Trop de sessions actives."}, status_code=429)
        value = secrets.token_urlsafe(32)
        sessions[value] = now + TTL
        response = JSONResponse({"status": "connected"})
        response.set_cookie(COOKIE, value + "." + signature(value), max_age=TTL,
                            httponly=True, secure=secure_cookie, samesite="strict")
        return response

    @app.post("/auth/logout")
    def logout(request: Request):
        if not same_origin(request):
            return JSONResponse({"detail": "Origine refusée."}, status_code=403)
        value = request.cookies.get(COOKIE, "").rpartition(".")[0]
        sessions.pop(value, None)
        response = JSONResponse({"status": "disconnected"})
        response.delete_cookie(COOKIE)
        return response
