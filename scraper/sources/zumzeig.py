"""Zumzeig (https://zumzeigcine.coop).

Fuente elegida tras comparar (29/10/2026):
  - /es/cine/sesiones/   agenda semanal + tarjetas recortadas a 3 sesiones con "+": incompleta.
  - codetickets.com      aplicación JS sin datos en el HTML: inútil sin navegador.
  - /es/cine/calendari/  calendario mensual con TODAS las sesiones (mes actual y siguientes):
                           td.day[rel=YYYY-MM-DD] > a.sessio[href=ficha] > .hora "18:00*" + .film
                         Contiene todas las fechas de las tarjetas de /sesiones/ y muchas más.
Así que: calendario para las sesiones + ficha de cada película con sesiones futuras para
  - la versión ("Versión: VOSE" / "Versión: VO, Ju 29.10.26 VOCAP" + "Idioma original: Castellano"),
    que puede traer excepciones por día
  - el enlace de compra de las próximas 3 sesiones (aside.compralateral a.s "Ma 3.11.26 (12:00)")
    y el "+" a la página de la película en codetickets, que se usa para el resto.
Un asterisco tras la hora marca sesiones especiales (presentación, coloquio, festival).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import load_config, tz
from ..http import Http
from ..models import Session, normalize_version

log = logging.getLogger(__name__)

BASE = "https://zumzeigcine.coop/"
CALENDAR_URL = "https://zumzeigcine.coop/es/cine/calendari/"
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(\*)?")
# 'Mi 28.10.26' (el día de la semana es opcional)
_DATE_RE = re.compile(r"(?:\b[A-Za-zÀ-ÿ]{2}\s+)?\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b")
_BUY_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*\((\d{1,2}):(\d{2})\)")


def parse_calendar(html: bytes | str) -> list[dict]:
    """Todas las sesiones del calendario: dicts con date, time, special, title, film_url."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for td in soup.select("td.day[rel]"):
        try:
            day = date.fromisoformat(td["rel"])
        except ValueError:
            continue
        for a in td.select("a.sessio"):
            hora = a.select_one(".hora")
            film = a.select_one(".film")
            m = _TIME_RE.search(hora.get_text(strip=True)) if hora else None
            if not m or not film:
                continue
            out.append({
                "date": day.isoformat(),
                "time": f"{int(m.group(1)):02d}:{m.group(2)}",
                "special": bool(m.group(3)),
                "title": film.get_text(" ", strip=True),
                "film_url": urljoin(BASE, a["href"]) if a.get("href") else None,
            })
    return out


def _field(soup: BeautifulSoup, label: str) -> str:
    """Valor de una línea 'Etiqueta: valor' de la ficha técnica."""
    for p in soup.select("p"):
        text = p.get_text(" ", strip=True).replace("\xa0", " ")
        if text.startswith(label + ":"):
            return text[len(label) + 1:].strip()
    return ""


def text_version(text: str, original_language: str) -> str:
    """Versión de un texto suelto: 'VOSE', 'VOSI', 'VO', 'VOCAP', 'Doblada al catalán'...

    'VO' (o VOCAP, VO con subtítulos para sordos) en una película en castellano o catalán
    no es VOSE: se oye en ese idioma. Como en las otras fuentes, castellano -> 'Doblada'.
    """
    head = text.split(" - ")[0].strip()  # 'VOSE - VOSI' -> la primera
    if re.fullmatch(r"V\.?\s?O\.?(\s?CAP)?", head, re.I):
        lang = normalize_version(original_language, default="")
        return lang if lang in ("Doblada", "Català") else "VOSE"
    return normalize_version(head, default="VOSE")  # Zumzeig proyecta todo en VO


def parse_version_field(raw: str, original_language: str) -> tuple[str, str, dict[str, tuple[str, str]]]:
    """'Versión:' de la ficha -> (versión, texto, excepciones {fecha ISO: (versión, texto)}).

    Ejemplos reales: 'VOSE' · 'VO, Ju 29.10.26 VOCAP (amb subtítols...)' ·
    'Mi 28.10.26 y Mi 4.11.26 VOSCAT, el resto VOSE' · 'VOSI - VOSF' · '' (+ 'Sin diálogos').
    """
    if not raw.strip():
        if "diálogo" in original_language.lower() or "diàleg" in original_language.lower():
            return "Desconocida", "Sin diálogos", {}
        return "VOSE", "", {}

    default: tuple[str, str] | None = None
    overrides: dict[str, tuple[str, str]] = {}
    for seg in raw.split(","):
        seg = re.sub(r"\(.*?\)", "", seg).strip()  # notas entre paréntesis
        dates = []
        for m in _DATE_RE.finditer(seg):
            d, mo, y = m.groups()
            try:
                dates.append(date(int(y) + 2000 if len(y) == 2 else int(y), int(mo), int(d)).isoformat())
            except ValueError:
                pass
        text = _DATE_RE.sub(" ", seg)
        text = re.sub(r"\b(y|i|el resto|la resta|resto|resta)\b", " ", text, flags=re.I)
        text = " ".join(text.split())
        if not text:
            continue
        version = (text_version(text, original_language), text)
        if dates:
            for d in dates:
                overrides[d] = version
        elif default is None or re.search(r"\b(resto|resta)\b", seg, re.I):
            default = version
    default = default or ("VOSE", raw.strip())
    return default[0], default[1], overrides


def parse_film(html: bytes | str) -> dict:
    """De la ficha: versión (con excepciones por día), tickets {(date, time): url} y more_url (el '+')."""
    soup = BeautifulSoup(html, "lxml")
    language = _field(soup, "Idioma original")
    version, version_raw, overrides = parse_version_field(
        _field(soup, "Versión") or _field(soup, "Versió"), language)
    tickets: dict[tuple[str, str], str] = {}
    more_url = None
    for a in soup.select("aside.compralateral a[href*='codetickets']"):
        m = _BUY_RE.search(a.get_text(" ", strip=True))
        if m:
            d, mo, y, hh, mm = m.groups()
            year = int(y) + 2000 if len(y) == 2 else int(y)
            try:
                key = (date(year, int(mo), int(d)).isoformat(), f"{int(hh):02d}:{mm}")
            except ValueError:
                continue
            tickets[key] = a["href"]
        elif a.get_text(strip=True) == "+":
            more_url = a["href"]
    return {
        "version": version,
        "version_raw": version_raw,
        "overrides": overrides,
        "tickets": tickets,
        "more_url": more_url,
    }


def build_sessions(calendar: list[dict], films: dict[str, dict], cinema: dict, today: date) -> list[Session]:
    sessions = []
    for c in calendar:
        if date.fromisoformat(c["date"]) < today:
            continue  # el calendario incluye el mes entero
        info = films.get(c["film_url"]) or {}
        ticket = (info.get("tickets", {}).get((c["date"], c["time"]))
                  or info.get("more_url")
                  or cinema.get("tickets_url"))
        version, version_raw = info.get("overrides", {}).get(
            c["date"], (info.get("version", "VOSE"), info.get("version_raw", "")))
        sessions.append(Session(
            cinema_id=cinema["id"],
            cinema_name=cinema["name"],
            film_title=c["title"],
            date=c["date"],
            time=c["time"],
            version=version,
            version_raw=version_raw,
            ticket_url=ticket,
            film_url=c["film_url"],
            special=c["special"],
            source="zumzeig",
        ))
    return sessions


def fetch(cinema: dict, http: Http | None = None, today: date | None = None) -> list[Session]:
    http = http or Http()
    if today is None:
        today = datetime.now(tz(load_config())).date()
    calendar = parse_calendar(http.get(cinema.get("url", CALENDAR_URL)).content)
    upcoming = [c for c in calendar if date.fromisoformat(c["date"]) >= today]
    films: dict[str, dict] = {}
    for url in dict.fromkeys(c["film_url"] for c in upcoming if c["film_url"]):
        try:
            films[url] = parse_film(http.get(url).content)
        except Exception as e:  # sin ficha: versión por defecto y enlace genérico
            log.warning("Zumzeig: error en %s: %s", url, e)
    return build_sessions(calendar, films, cinema, today)
