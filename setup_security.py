"""Configuration locale : les secrets restent dans .env, exclu de Git."""
import getpass
import secrets
from pathlib import Path
from security import password_hash


def main():
    path = Path(__file__).resolve().parent / ".env"
    previous = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if "SENTINEL_PASSWORD_HASH=" in previous:
        print("Sécurité déjà configurée dans .env. Aucun accès modifié.")
        return
    while True:
        password = getpass.getpass("Choisis un mot de passe dashboard (12 caractères minimum) : ")
        if len(password) < 12:
            print("Le mot de passe doit contenir au moins 12 caractères.")
            continue
        if password == getpass.getpass("Confirme ce mot de passe : "):
            break
        print("Les deux saisies sont différentes.")
    values = {"SENTINEL_PASSWORD_HASH": password_hash(password),
              "SENTINEL_SESSION_SECRET": secrets.token_urlsafe(48),
              "SENTINEL_BRIDGE_KEY": secrets.token_urlsafe(32),
              "SENTINEL_VISION_KEY": secrets.token_urlsafe(32),
              "SENTINEL_COOKIE_SECURE": "false"}
    kept = [line for line in previous.splitlines() if line.partition("=")[0] not in values]
    content = "\n".join(kept + [f"{key}={value}" for key, value in values.items()]) + "\n"
    temporary = path.with_name(".env.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    print("Accès configurés. Garde .env sur ton PC ; ne le pousse pas sur Git.")


if __name__ == "__main__":
    main()
