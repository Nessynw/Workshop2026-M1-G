"""Configuration locale et clés des clients ; aucune clé dans le navigateur."""
import os
from pathlib import Path


def load_environment():
    path = Path(__file__).resolve().parent / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def service_headers(role):
    load_environment()
    token = os.environ.get(f"SENTINEL_{role.upper()}_KEY", "")
    if len(token) < 32:
        raise RuntimeError("Accès API absent : exécuter setup_security.py avant de lancer ce service.")
    return {"Authorization": "Bearer " + token}
