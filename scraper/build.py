"""Filtro de matinées: data/sessions.json -> docs/matinees.json.

    python -m scraper.build
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, time, timedelta

from .config import ROOT, load_config, tz
from .models import Session
from .run import SESSIONS_PATH, write_json

log = logging.getLogger("scraper.build")

MATINEES_PATH = ROOT / "docs" / "matinees.json"


def is_matinee(s: Session, today: date, cutoff: time, weekdays: list[int], horizon_days: int) -> bool:
    """Sesión dentro del horizonte (de hoy a hoy + horizon_days - 1), en día incluido
    y que empieza como tarde a la hora de corte (inclusive)."""
    d = date.fromisoformat(s.date)
    t = datetime.strptime(s.time, "%H:%M").time()
    return today <= d < today + timedelta(days=horizon_days) and d.weekday() in weekdays and t <= cutoff


def filter_matinees(sessions: list[Session], now: datetime, cfg: dict) -> list[Session]:
    """Aplica el filtro de config.yaml y ordena por fecha, hora, cine y película.

    `now` debe estar ya en la zona horaria del config (Europe/Madrid).
    """
    m = cfg["matinee"]
    cutoff = datetime.strptime(m["cutoff"], "%H:%M").time()
    weekdays = list(m["weekdays"])
    horizon = int(m.get("horizon_days", 14))
    today = now.date()
    out = [s for s in sessions if s.is_valid() and is_matinee(s, today, cutoff, weekdays, horizon)]
    out.sort(key=lambda s: (s.date, s.time, s.cinema_name, s.film_title))
    return out


def build(data: dict, now: datetime, cfg: dict) -> dict:
    """Documento de docs/matinees.json: meta de sessions.json + filtro aplicado + sesiones."""
    sessions = [Session.from_dict(d) for d in data.get("sessions", [])]
    meta = dict(data.get("meta", {}))
    meta.update(
        built_at=now.isoformat(timespec="seconds"),
        filter={k: cfg["matinee"][k] for k in ("cutoff", "weekdays", "horizon_days")},
    )
    return {"meta": meta, "sessions": [s.to_dict() for s in filter_matinees(sessions, now, cfg)]}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    with open(SESSIONS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    doc = build(data, datetime.now(tz(cfg)), cfg)
    write_json(doc, MATINEES_PATH, compact=True)
    log.info("%d matinées de %d sesiones -> %s", len(doc["sessions"]), len(data.get("sessions", [])),
             MATINEES_PATH.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
