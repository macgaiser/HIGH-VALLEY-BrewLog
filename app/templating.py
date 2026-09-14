import json
import os

from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlmodel import Session

from app.database import engine
from app.models import BackgroundImage, Settings

templates = Jinja2Templates(directory="app/templates")

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _static_version(filename: str) -> str:
    """Cache-Busting fuer /static/style.css und /static/app.js: haengt die
    Aenderungszeit der Datei als Query-Parameter an, damit Browser nach
    jedem Deploy garantiert die neue Version laden statt (wie zuvor
    beobachtet) auf der alten CSS/JS unter derselben URL sitzen zu bleiben,
    waehrend die serverseitig gerenderten HTML-Seiten schon aktuell sind."""
    try:
        mtime = int(os.path.getmtime(os.path.join(_STATIC_DIR, filename)))
    except OSError:
        return ""
    return f"?v={mtime}"


templates.env.globals["static_version"] = _static_version


def _background_image_url() -> str:
    """Aktives Hintergrundbild ("Tal") - dieselbe Datei fuer den App-weiten
    Hintergrund (body::before, jede Seite) und das Marken-Feld auf dem
    Etikett (.label-brand::before), siehe --bg-valley-url in base.html/
    style.css. Anders als bei Logo/Rahmengrafik wird hier direkt in
    base.html aufgerufen (nicht ueber den jeweiligen Router durchgereicht),
    weil der App-Hintergrund auf jeder Seite gebraucht wird, nicht nur auf
    dem Etikett - eine eigene, kurze DB-Abfrage ist dafuer einfacher als das
    Settings-Objekt durch jede einzelne Route zu schleifen. Faellt ohne
    eigenen Upload auf das eingebaute bg-valley.png zurueck."""
    default_url = "/static/img/bg-valley.png"
    with Session(engine) as session:
        s = session.get(Settings, 1)
        if s and s.active_background_image_id:
            img = session.get(BackgroundImage, s.active_background_image_id)
            if img:
                return f"/background-images/{img.filename}"
    return default_url


templates.env.globals["background_image_url"] = _background_image_url

# Vom Docker-Build gesetzter Git-Commit-Hash (siehe Dockerfile ARG GIT_SHA /
# .github/workflows/docker-publish.yml) - fuer die Fusszeile, damit man auf
# der laufenden Instanz sieht welcher Stand deployed ist (nuetzlich mit
# Watchtower-Auto-Update). Ausserhalb von Docker (lokaler Dev-Server) gibt es
# keinen Build-Schritt, der das setzen wuerde, daher der "dev"-Fallback.
templates.env.globals["app_version"] = os.environ.get("APP_VERSION", "dev")
templates.env.globals["github_repo_url"] = "https://github.com/macgaiser/HIGH-VALLEY-BrewLog"


def _fmt(value, decimals: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value:.{decimals}f}"


def _de_date(value) -> str:
    if value is None:
        return "–"
    return value.strftime("%d.%m.%Y")


def _de_date_short(value) -> str:
    if value is None:
        return "–"
    return value.strftime("%d.%m.%y")


def _tojson(value) -> Markup:
    """Fuer Chart.js-Daten im <script>-Block der Statistik-Seite: reines
    Jinja2 (anders als Flask) bringt keinen tojson-Filter mit. Escaped die
    fuer JSON-in-HTML kritischen Zeichen (Flask-kompatibel) und markiert das
    Ergebnis als bereits sicher, damit Jinjas Auto-Escaping die JSON-
    Anfuehrungszeichen nicht zusaetzlich in HTML-Entities verwandelt."""
    raw = json.dumps(value)
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("'", "\\u0027")
    return Markup(raw)


templates.env.filters["fmt"] = _fmt
templates.env.filters["de_date"] = _de_date
templates.env.filters["de_date_short"] = _de_date_short
templates.env.filters["tojson"] = _tojson
