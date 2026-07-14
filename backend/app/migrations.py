"""Programmatic Alembic runner, called from init_db() at API startup.

Handles three deployment states:
  * Fresh database            -> upgrade to head (runs all migrations).
  * Pre-Alembic database      -> stamp the matching baseline first, then upgrade.
    (v1 created tables via create_all with no alembic_version table; we detect
    which schema generation it is by looking for the v1.x consent column.)
  * Already-migrated database -> upgrade is a no-op.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import settings
from .database import engine

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    # %% escaped for configparser (passwords may contain %).
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return cfg


def run_migrations() -> None:
    cfg = _alembic_config()
    insp = inspect(engine)
    if insp.has_table("students") and not insp.has_table("alembic_version"):
        cols = {c["name"] for c in insp.get_columns("students")}
        baseline = "0002" if "consent_recorded_at" in cols else "0001"
        command.stamp(cfg, baseline)
    command.upgrade(cfg, "head")
