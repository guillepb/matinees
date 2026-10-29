"""Cines Verdi Barcelona (https://barcelona.cines-verdi.com) y otros cines con la misma web.

La misma plataforma la usa Cinemes Girona (https://www.cinemesgirona.cat): el dominio sale de
cinema["url"], así que basta con `source: verdi` en config.yaml.

Estructura observada (29/10/2026):
  /cartelera                  ul.collection > li > article .aside a[href]  -> slugs de película
                              (las sesiones de esta página se cargan por JS: solo sirve para los slugs)
  /<slug>                     h1 título; section.performances-vert alterna:
                                div > time  "jueves 29 OCT 2026" / "dijous 29 D'OCT 2026"
                                div > a[href=admit-one/seats/<id>/]  time "11:30" + small "CASTELLÀ"
                                       x-show="!isPast('20261029113000')"  (fecha y hora completas)
Idioma: ?lang=es fija el castellano en la cookie de sesión; el parser entiende ambos.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..http import Http
from ..models import Session, normalize_version

log = logging.getLogger(__name__)

BASE = "https://barcelona.cines-verdi.com/"

# Primeras tres letras, sin acentos, en castellano y catalán
MONTHS = {
    "ENE": 1, "GEN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "MAI": 5,
    "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11,
    "DIC": 12, "DES": 12,
}
_DAY_RE = re.compile(r"(\d{1,2})\s+(?:D['’]\s*|DE\s+)?([A-Z]{3})[A-Z]*\.?\s+(\d{4})")
_STAMP_RE = re.compile(r"isPast\('(\d{12})")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def parse_day(text: str) -> date | None:
    """'jueves 29 OCT 2026' / 'dijous 29 D’OCT 2026' / 'dimarts 27 de nov. 2026' -> date."""
    m = _DAY_RE.search(_fold(text))
    if not m or m.group(2) not in MONTHS:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def _base(url: str) -> str:
    """'https://www.cinemesgirona.cat/cartelera' -> 'https://www.cinemesgirona.cat/'."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def parse_listing(html: bytes | str, base: str = BASE) -> list[str]:
    """URLs absolutas de las fichas de película de la cartelera, sin repetir."""
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for a in soup.select("ul.collection > li article .aside a[href]"):
        url = urljoin(base, a["href"].split("?")[0])
        if url not in urls:
            urls.append(url)
    return urls


def parse_film(html: bytes | str, cinema: dict, film_url: str) -> list[Session]:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    box = soup.select_one("section.performances-vert")
    if not title or not box:
        return []

    sessions: list[Session] = []
    current: date | None = None
    for div in box.find_all("div", recursive=False):
        header = div.find("time", recursive=False)
        if header is not None:
            current = parse_day(header.get_text(" ", strip=True))
            continue
        for a in div.find_all("a", href=True):
            t = a.find("time")
            tm = _TIME_RE.search(t.get_text(strip=True)) if t else None
            if not tm:
                continue
            hhmm = f"{int(tm.group(1)):02d}:{tm.group(2)}"
            day = current
            stamp = _STAMP_RE.search(a.get("x-show", ""))
            if stamp:  # la fecha completa del atributo manda sobre la cabecera
                day = datetime.strptime(stamp.group(1), "%Y%m%d%H%M").date()
            if day is None:
                continue
            small = a.find("small")
            version_raw = small.get_text(" ", strip=True) if small else ""
            sessions.append(Session(
                cinema_id=cinema["id"],
                cinema_name=cinema["name"],
                film_title=title,
                date=day.isoformat(),
                time=hhmm,
                version=normalize_version(version_raw),
                version_raw=version_raw,
                ticket_url=a["href"] if "admit-one" in a["href"] else cinema.get("tickets_url"),
                film_url=film_url,
                special=False,
                source="verdi",
            ))
    sessions.sort(key=lambda s: (s.date, s.time))
    return sessions


def fetch(cinema: dict, http: Http | None = None, today: date | None = None) -> list[Session]:
    http = http or Http()
    base = _base(cinema["url"])
    name = cinema["name"]
    # La primera petición con ?lang=es deja el castellano en la cookie de sesión
    listing = http.get(cinema["url"], params={"lang": "es"})
    sessions: list[Session] = []
    errors = 0
    urls = parse_listing(listing.content, base)
    if not urls:  # visto una vez desde GitHub Actions, de forma puntual: un segundo intento
        log.warning("%s: cartelera sin películas, reintentando en 10 s", name)
        time.sleep(10)
        listing = http.get(cinema["url"], params={"lang": "es"})
        urls = parse_listing(listing.content, base)
    if not urls:
        soup = BeautifulSoup(listing.content, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else ""
        raise RuntimeError(
            f"cartelera sin películas (HTTP {listing.status_code}, {len(listing.content)} bytes, "
            f"url={listing.url}, título={title!r}, texto={soup.get_text(' ', strip=True)[:160]!r})")
    for url in urls:
        try:
            sessions += parse_film(http.get(url).content, cinema, url)
        except Exception as e:  # una ficha rota no tumba la fuente entera
            errors += 1
            log.warning("%s: error en %s: %s", name, url, e)
    if urls and errors == len(urls):
        raise RuntimeError(f"{name}: fallaron las {errors} fichas")
    return sessions
