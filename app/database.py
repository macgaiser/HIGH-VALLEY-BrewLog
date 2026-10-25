import os
import shutil
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 - muss vor create_all()/_add_missing_columns()
# importiert sein, damit SQLModel.metadata die Tabellen überhaupt kennt.
# Wird sonst nur zufällig durch die Importreihenfolge anderer Module
# sichergestellt (z.B. weil main.py die Router importiert, die ihrerseits
# app.models importieren) - das ist fragil, u.a. bricht init_db() sonst
# lautlos (create_all() legt dann null Tabellen an), wenn es als erstes
# aus einem Skript aufgerufen wird, das app.models noch nicht kennt.

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "brewlog.db"

LOGO_DIR = DATA_DIR / "logos"
LOGO_DIR.mkdir(parents=True, exist_ok=True)

BORDER_GRAPHIC_DIR = DATA_DIR / "border_graphics"
BORDER_GRAPHIC_DIR.mkdir(parents=True, exist_ok=True)

BACKGROUND_IMAGE_DIR = DATA_DIR / "background_images"
BACKGROUND_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def _add_missing_columns() -> None:
    """Kleine, bewusst simple Selbst-Migration: legt beim Start neue Spalten
    an, die eine neuere Version des Modells kennt, die eigentliche
    SQLite-Datei aber noch nicht hat - so bricht die App nach einem
    Update nicht direkt mit "no such column" ab, wie es sonst der Fall
    wäre, weil `create_all()` nur komplett fehlende Tabellen anlegt,
    bestehende Tabellen aber nicht verändert.

    Deckt nur den (in dieser App bisher einzig vorkommenden) Fall neuer,
    nullable bzw. mit einfachem Skalar-Default versehener Spalten ab -
    keine vollständige Migration (keine umbenannten/gelöschten Spalten,
    keine Typänderungen). Für sowas bräuchte es ein echtes
    Migrationswerkzeug wie Alembic.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(conn.dialect)
                default_sql = ""
                default = column.default
                if default is not None and getattr(default, "is_scalar", False):
                    value = default.arg
                    if isinstance(value, bool):
                        default_sql = f" DEFAULT {int(value)}"
                    elif isinstance(value, (int, float)):
                        default_sql = f" DEFAULT {value}"
                    elif isinstance(value, str):
                        default_sql = f" DEFAULT '{value}'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}'))


_DEFAULT_BEER_STYLES = [
    "Helles",
    "Pils",
    "Export",
    "Märzen/Festbier",
    "Weizen (Hefeweizen)",
    "Kölsch",
    "Alt",
    "Bockbier",
    "Dunkles/Schwarzbier",
    "IPA",
    "Pale Ale",
    "APA",
    "NEIPA",
    "Stout/Porter",
    "Barleywine",
    "Saison",
    "Sauerbier (Berliner Weisse/Gose)",
]


# Vorlage fuer neue Installationen: nur die Tätigkeiten, bewusst OHNE Zeiten -
# die Dauer ist von Brauanlage und Arbeitsweise abhängig und wird je Sud bzw.
# unter Einstellungen eingetragen.
_DEFAULT_BREW_DAY_TASKS = [
    ("Vorbereiten + Schroten", None, ""),
    ("Eingemeischt", None, ""),
    ("Läutern + Hopfen vorbereiten", None, ""),
    ("Malzrohr putzen", None, ""),
    ("Hopfengaben", None, ""),
    ("Kühlung aufbauen", None, ""),
    ("Whirlpool und abkühlen", None, ""),
    ("Abfüllen, putzen", None, ""),
    ("Schläuche aufräumen, putzen", None, ""),
    ("Keg reinigen", None, ""),
    ("In Keg abfüllen", None, ""),
    ("Flaschen abfüllen", None, ""),
    ("Rezept vorbereiten", None, ""),
]


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    with Session(engine) as session:
        from app.models import BeerStyle, DefaultBrewDayTask, Settings

        if session.get(Settings, 1) is None:
            session.add(Settings(id=1))
            session.commit()

        if session.exec(select(DefaultBrewDayTask)).first() is None:
            for i, (name, duration, note) in enumerate(_DEFAULT_BREW_DAY_TASKS):
                session.add(
                    DefaultBrewDayTask(position=i, task_name=name, planned_duration_min=duration, note=note)
                )
            session.commit()

        if session.exec(select(BeerStyle)).first() is None:
            for i, name in enumerate(_DEFAULT_BEER_STYLES):
                session.add(BeerStyle(position=i, name=name))
            session.commit()

        _fix_hop_alpha_fractions(session)
        _auto_lock_old_costs(session)
        _keep_legacy_label_logo(session)


_LABEL_LOGO_MARKER = DATA_DIR / ".migrated-label-logo-v1"


def _keep_legacy_label_logo(session: Session) -> None:
    """Einmalige Uebernahme fuer Bestandsinstallationen: Das eingebaute
    Standard-Logo des Etikettengenerators war frueher das Wappen und ist jetzt
    der neutrale Bierkrug. Wer bisher kein eigenes Logo aktiv hatte (also das
    eingebaute Wappen auf seinen Etiketten nutzte), behaelt sein Aussehen: das
    Wappen wird als hochgeladenes Logo angelegt und als Standard gesetzt.
    Frische Installationen (noch keine Sude) bekommen den Bierkrug. Laeuft
    genau einmal (Marker-Datei im Datenordner)."""
    from app.models import Batch, Logo, Settings

    if _LABEL_LOGO_MARKER.exists():
        return
    settings = session.get(Settings, 1)
    existing_install = session.exec(select(Batch)).first() is not None
    legacy_shield = Path(__file__).parent / "static" / "img" / "logo-shield.png"
    if settings and settings.active_logo_id is None and existing_install and legacy_shield.exists():
        stored_name = f"{uuid.uuid4().hex}.png"
        shutil.copyfile(legacy_shield, LOGO_DIR / stored_name)
        logo = Logo(
            filename=stored_name,
            original_filename="logo-shield.png",
            scale_percent=settings.default_logo_scale,
        )
        session.add(logo)
        session.flush()
        settings.active_logo_id = logo.id
        session.add(settings)
        session.commit()
    _LABEL_LOGO_MARKER.write_text("Einmalige Logo-Uebernahme erledigt - Datei nicht loeschen.\n")


def _fix_hop_alpha_fractions(session: Session) -> None:
    """Einmalige Korrektur alter Lagerartikel-Daten: der ursprüngliche
    Excel-Import hatte die Alphasäure von Hopfen als Bruch abgelegt (z.B.
    "0,183" statt "18,3") in InventoryItem.spec. Werte, die eindeutig als
    Bruch erkennbar sind (kleiner als 1 - eine Alphasäure unter 1% kommt in
    der Praxis nicht vor), werden beim Start auf Prozent umgerechnet.
    Idempotent: bereits korrigierte Werte (>= 1) bleiben unangetastet, ein
    erneuter Lauf ändert dann nichts mehr."""
    from app.models import InventoryCategory, InventoryItem

    items = session.exec(select(InventoryItem).where(InventoryItem.category == InventoryCategory.hopfen)).all()
    changed = False
    for item in items:
        raw = (item.spec or "").strip().replace(",", ".")
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 < value < 1:
            item.spec = f"{value * 100:.1f}"
            session.add(item)
            changed = True
    if changed:
        session.commit()


def _auto_lock_old_costs(session: Session) -> None:
    """Sammel-Durchlauf beim Start: sperrt die Kostenrechnung (siehe
    batch_calc.auto_lock_cost/Batch.cost_locked) für alle bereits
    vorhandenen Sude, deren Brautag mehr als AUTO_LOCK_AGE_DAYS zurückliegt
    - ohne diesen Durchlauf würde das automatische Sperren erst greifen,
    sobald jemand den einzelnen Sud zufällig aufruft (siehe batch_detail in
    routers/batches.py, wo dieselbe Funktion für neu alternde Sude auch im
    laufenden Betrieb greift). So sind bereits bestehende alte Sude sofort
    nach dem nächsten Start erfasst, nicht erst nach manuellem Aufrufen
    jedes einzelnen. Idempotent: bereits gesperrte Sude werden
    übersprungen, ein erneuter Lauf ändert dann nichts mehr."""
    from app.batch_calc import auto_lock_cost
    from app.models import Batch, Settings

    settings = session.get(Settings, 1)
    if settings is None:
        return
    today = date.today()
    changed = False
    for batch in session.exec(select(Batch)).all():
        if auto_lock_cost(batch, settings, today):
            session.add(batch)
            changed = True
    if changed:
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
