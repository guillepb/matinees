"""Scraping diario: todas las fuentes de config.yaml -> data/sessions.json (sin filtrar).

    python -m scraper.run

Cada cine en su propio try: si falla (o devuelve 0 sesiones) se conservan sus sesiones
futuras de la ejecución anterior y se marca stale. Sale con código 1 si fallan todos.
"""
from __future__ import annotations

import importlib
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .config import ROOT, load_config, tz
from .http import Http
from .models import Session

log = logging.getLogger("scraper.run")

SESSIONS_PATH = ROOT / "data" / "sessions.json"

Fetcher = Callable[[dict, Http, date], list[Session]]


def load_previous(path: Path = SESSIONS_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"meta": {"sources": {}}, "sessions": []}


def clean(sessions: list[Session], today: date) -> list[Session]:
    """Fuera sesiones inválidas, pasadas o duplicadas (mismo cine, película, fecha y hora)."""
    seen: set[tuple] = set()
    out = []
    for s in sessions:
        if not s.is_valid() or date.fromisoformat(s.date) < today or s.key in seen:
            continue
        seen.add(s.key)
        out.append(s)
    return out


def _default_fetcher(source: str) -> Fetcher:
    module = importlib.import_module(f".sources.{source}", __package__)
    return lambda cinema, http, today: module.fetch(cinema, http=http, today=today)


def collect(cfg: dict, now: datetime, previous: dict,
            fetchers: dict[str, Fetcher] | None = None, http: Http | None = None) -> dict:
    """Ejecuta todas las fuentes y devuelve el documento completo {meta, sessions}."""
    fetchers = fetchers or {}
    http = http or Http()
    today = now.date()
    stamp = now.isoformat(timespec="seconds")
    prev_meta = previous.get("meta", {}).get("sources", {})
    prev_sessions = [Session.from_dict(d) for d in previous.get("sessions", [])]

    sessions: list[Session] = []
    status: dict[str, dict] = {}
    for cinema in cfg["cinemas"]:
        cid = cinema["id"]
        entry = {"name": cinema["name"], "source": cinema["source"]}
        try:
            fetch = fetchers.get(cinema["source"]) or _default_fetcher(cinema["source"])
            got = clean(fetch(cinema, http, today), today)
            if not got:
                raise RuntimeError("0 sesiones (posible cambio en la web)")
            sessions += got
            entry.update(status="ok", message=None, count=len(got), stale=False, last_ok=stamp,
                         last_date=max(s.date for s in got))
            log.info("%-16s ok    %4d sesiones", cid, len(got))
        except Exception as e:
            kept = clean([s for s in prev_sessions if s.cinema_id == cid], today)
            sessions += kept
            prev = prev_meta.get(cid, {})
            entry.update(status="error", message=f"{type(e).__name__}: {e}"[:300], count=len(kept),
                         stale=bool(kept), last_ok=prev.get("last_ok"),
                         last_date=max((s.date for s in kept), default=None))
            log.error("%-16s ERROR %s (se conservan %d sesiones anteriores)", cid, e, len(kept))
        status[cid] = entry

    sessions.sort(key=lambda s: (s.date, s.time, s.cinema_id, s.film_title))
    return {
        "meta": {"generated_at": stamp, "timezone": cfg["timezone"], "sources": status},
        "sessions": [s.to_dict() for s in sessions],
    }


def write_json(doc: dict, path: Path, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    now = datetime.now(tz(cfg))
    doc = collect(cfg, now, load_previous())
    write_json(doc, SESSIONS_PATH)
    sources = doc["meta"]["sources"].values()
    log.info("%d sesiones -> %s", len(doc["sessions"]), SESSIONS_PATH.name)
    if sources and all(s["status"] == "error" for s in sources):
        log.error("Han fallado todas las fuentes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
