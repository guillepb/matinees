import pytest

from scraper.models import Session, normalize_version


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("DIGITAL", "Doblada"),
        ("CASTELLÀ", "Doblada"),
        ("CASTELLANO", "Doblada"),
        ("VOSE", "VOSE"),
        ("V.O. SUB. CASTELLÀ", "VOSE"),
        ("V.O. Sub. Castellano", "VOSE"),
        ("V.O. SUB. INGLÉS", "VOSE inglés"),
        ("V.O. SUB. ANGLÈS", "VOSE inglés"),
        ("CATALÀ", "Català"),
        ("  català ", "Català"),
        ("", "Desconocida"),
        (None, "Desconocida"),
        ("IMAX LASER", "Desconocida"),
    ],
)
def test_normalize_version(raw, expected):
    assert normalize_version(raw) == expected


def test_normalize_version_default():
    # Zumzeig proyecta todo en VO: su parser pasa VOSE como valor por defecto
    assert normalize_version("", default="VOSE") == "VOSE"


def _s(**kw):
    base = dict(
        cinema_id="verdi", cinema_name="Cines Verdi", film_title="La bola negra",
        date="2026-10-28", time="11:30", version="Doblada", version_raw="CASTELLÀ",
        ticket_url=None, film_url=None, special=False, source="verdi",
    )
    base.update(kw)
    return Session(**base)


def test_session_roundtrip():
    s = _s()
    assert Session.from_dict(s.to_dict()) == s


@pytest.mark.parametrize("time", ["25:00", "11:60", "1130", ""])
def test_invalid_time(time):
    assert not _s(time=time).is_valid()


def test_invalid_date():
    assert not _s(date="2026-02-30").is_valid()


def test_dedup_key_ignores_case():
    assert _s(film_title="La Bola Negra").key == _s().key
