"""Modelo de sesión común a todas las fuentes y normalización de versiones."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime

VERSIONS = ("Doblada", "VOSE", "VOSE inglés", "Català", "Desconocida")


@dataclass
class Session:
    cinema_id: str
    cinema_name: str
    film_title: str
    date: str  # YYYY-MM-DD, hora local de Madrid
    time: str  # HH:MM, 24 h
    version: str
    version_raw: str
    ticket_url: str | None
    film_url: str | None
    special: bool
    source: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})

    @property
    def key(self) -> tuple:
        """Clave de deduplicación: mismo cine, película, fecha y hora."""
        return (self.cinema_id, self.film_title.casefold().strip(), self.date, self.time)

    def is_valid(self) -> bool:
        try:
            date.fromisoformat(self.date)
            datetime.strptime(self.time, "%H:%M")
        except (TypeError, ValueError):
            return False
        return bool(self.film_title and self.film_title.strip())


def _fold(text: str) -> str:
    """Mayúsculas, sin acentos y sin puntuación: 'V.O. Sub. Inglés' -> 'V O SUB INGLES'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return text.upper().strip()


# Reglas en orden: la primera que encaje gana. Se comparan contra el texto "plegado".
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(INGLES|ANGLES|ENGLISH|ENG|VOSI)\b"), "VOSE inglés"),
    (re.compile(r"\b(VOSE|VOS|VOSC|VOSCAT|VO|V O|SUB|SUBT|SUBTITULADA)\b"), "VOSE"),
    (re.compile(r"\b(CATALA|CATALAN)\b"), "Català"),
    (re.compile(r"\b(DIGITAL|CASTELLA|CASTELLANO|ESPANOL|DOBLADA|3D|2D)\b"), "Doblada"),
]


def normalize_version(raw: str | None, default: str = "Desconocida") -> str:
    """Normaliza el texto de versión de cualquier fuente a uno de VERSIONS."""
    if not raw or not raw.strip():
        return default
    folded = _fold(raw)
    for pattern, version in _RULES:
        if pattern.search(folded):
            return version
    return default
