"""FilmAgenda: parser genérico para cualquier página de cine
(https://www.filmagenda.es/cine/<slug>).

Estructura observada (01/11/2026): las sesiones van en el HTML, dentro del payload de Next.js
(self.__next_f.push), como un objeto JSON "sessions":
  films  [{title_es, title, primary_language: ["es"], canonical_slug, ...}]
  notes  [{tag: "coloquio", label_es, ...}]
  rows   [[id, film, "2026-11-02T11:30:00", venue, url_compra, url_info, version, gratis, [notas]]]
         film y notas son índices; version es "vose" | "dubbed" | null.

Ojo: "vose" significa en realidad versión original, también en películas españolas.
Es un formato interno sin documentar: si cambia, fetch() lanza un error y run.py lo registra.
"""
from __future__ import annotations

import json
import re
from datetime import date

from ..http import Http
from ..models import Session

BASE = "https://www.filmagenda.es"
_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_SESSIONS_KEY = '"sessions":{"films"'
# Notas que hacen especial una sesión (no lo son "notice", "free_entry", "discount", "shorts"...)
SPECIAL_TAGS = {
    "baby_friendly", "coloquio", "concert", "conference", "festival", "live_music", "opera",
    "ballet", "presentation", "program", "special_screening", "workshop",
}


def extract_sessions(html: bytes | str) -> dict:
    """Devuelve el objeto {films, notes, rows} embebido en la página."""
    raw = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    payload = "".join(json.loads(f'"{c}"') for c in _CHUNK_RE.findall(raw))
    start = payload.find(_SESSIONS_KEY)
    if start < 0:
        raise ValueError("no se encuentran las sesiones en el payload (posible cambio en la web)")
    obj, _ = json.JSONDecoder().raw_decode(payload[start + len('"sessions":'):])
    return obj


def version_of(raw: str | None, languages: list[str]) -> tuple[str, str]:
    """(versión, texto) a partir de la versión de la fila y el idioma original de la película."""
    if raw == "dubbed":
        return "Doblada", raw
    if raw != "vose":
        return "Desconocida", ""
    lang = languages[0] if languages else None
    if lang == "es":
        return "Doblada", raw  # como en las otras fuentes: se oye en castellano
    if lang == "ca":
        return "Català", raw
    return ("VOSE", raw) if lang else ("Desconocida", "VO")


def parse(html: bytes | str, cinema: dict) -> list[Session]:
    data = extract_sessions(html)
    films, notes = data["films"], data["notes"]
    sessions = []
    for _id, film_i, start, _venue, ticket, info, raw_version, _free, note_ids in data["rows"]:
        film = films[film_i]
        version, version_raw = version_of(raw_version, film.get("primary_language") or [])
        film_url = info or f"{BASE}/pelicula/{film['canonical_slug']}/barcelona"
        sessions.append(Session(
            cinema_id=cinema["id"],
            cinema_name=cinema["name"],
            film_title=film.get("title_es") or film["title"],
            date=start[:10],
            time=start[11:16],
            version=version,
            version_raw=version_raw,
            ticket_url=ticket or film_url or cinema.get("tickets_url"),
            film_url=film_url,
            special=any(notes[n]["tag"] in SPECIAL_TAGS for n in note_ids),
            source="filmagenda",
        ))
    return sessions


def fetch(cinema: dict, http: Http | None = None, today: date | None = None) -> list[Session]:
    http = http or Http()
    return parse(http.get(cinema["url"]).content, cinema)
