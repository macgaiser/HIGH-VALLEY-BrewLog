import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

# Bekannte Beispiel-/Standardwerte aus README, .env.example und
# docker-compose.yml - mit diesen darf die App nicht laufen, weil sie
# oeffentlich nachzulesen sind.
_INSECURE_PASSWORDS = {"", "brewlog", "changeme", "change-me-please", "admin", "password", "passwort"}


def require_secure_credentials() -> None:
    """Verweigert den Start ohne eigenes Passwort (APP_PASSWORD).

    Nur fuer lokale Entwicklung/Tests laesst sich die Pruefung mit
    APP_ALLOW_INSECURE_DEFAULTS=1 ausschalten (dann gelten die
    Standardwerte admin/brewlog)."""
    if os.environ.get("APP_ALLOW_INSECURE_DEFAULTS") == "1":
        return
    password = os.environ.get("APP_PASSWORD", "")
    if password.strip().lower() in _INSECURE_PASSWORDS:
        raise SystemExit(
            "\nSTART ABGEBROCHEN: Es ist kein eigenes Passwort gesetzt.\n"
            "Setze die Umgebungsvariable APP_PASSWORD auf ein eigenes, sicheres Passwort\n"
            "(und optional APP_USERNAME), z.B. in der .env neben der docker-compose.yml:\n"
            "    APP_USERNAME=admin\n"
            "    APP_PASSWORD=<dein-eigenes-passwort>\n"
            "Die bekannten Beispielwerte (brewlog, changeme, change-me-please, ...) sind nicht erlaubt.\n"
            "Nur fuer lokale Entwicklung: APP_ALLOW_INSECURE_DEFAULTS=1\n"
        )


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_user = os.environ.get("APP_USERNAME", "admin")
    expected_pass = os.environ.get("APP_PASSWORD", "brewlog")

    correct_username = secrets.compare_digest(credentials.username, expected_user)
    correct_password = secrets.compare_digest(credentials.password, expected_pass)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
