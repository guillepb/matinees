"""Cinemes Girona: misma plataforma que Verdi, se lee con scraper.sources.verdi."""
from pathlib import Path

from scraper.sources.verdi import parse_film, parse_listing

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://www.cinemesgirona.cat/"
CINEMA = {"id": "cinemes-girona", "name": "Cinemes Girona", "tickets_url": BASE + "cartelera"}


def test_parse_listing():
    urls = parse_listing((FIXTURES / "cinemesgirona_cartelera.html").read_bytes(), BASE)
    assert len(urls) == 83
    assert urls[:2] == [BASE + "la-bola-negra", BASE + "baga"]
    assert all(u.startswith(BASE) for u in urls)


def test_film_morning_session():
    ss = parse_film((FIXTURES / "cinemesgirona_baga.html").read_bytes(), CINEMA, BASE + "baga")
    assert [(s.film_title, s.date, s.time, s.version, s.version_raw) for s in ss] == [
        ("Baga", "2026-10-29", "10:00", "VOSE", "VOSE (Otras Lenguas)")]
    assert ss[0].ticket_url == "https://girona.admit-one.eu/?p=tickets&perfCode=40969&language=CAT"
    assert ss[0].cinema_id == "cinemes-girona"


def test_film_without_version():
    ss = parse_film((FIXTURES / "cinemesgirona_la-bola-negra.html").read_bytes(), CINEMA,
                    BASE + "la-bola-negra")
    # cabeceras "dilluns 02 DE NOV 2026" con el año aparte
    assert [(s.date, s.time) for s in ss] == [
        ("2026-11-02", "19:30"), ("2026-11-03", "17:00"), ("2026-11-04", "20:00"), ("2026-11-05", "20:00")]
    assert {s.version for s in ss} == {"Desconocida"}
    assert all("girona.admit-one.eu" in s.ticket_url for s in ss)
