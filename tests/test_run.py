from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scraper.build import build
from scraper.models import Session
from scraper.run import clean, collect

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 29, 6, 17, tzinfo=MADRID)  # jueves
CFG = {
    "timezone": "Europe/Madrid",
    "matinee": {"cutoff": "13:00", "weekdays": [0, 1, 2, 3, 4], "horizon_days": 14},
    "cinemas": [
        {"id": "a", "name": "Cine A", "source": "src_a"},
        {"id": "b", "name": "Cine B", "source": "src_b"},
    ],
}


def _s(cid="a", date="2026-10-30", time="11:00", title="Peli"):
    return Session(
        cinema_id=cid, cinema_name=f"Cine {cid.upper()}", film_title=title, date=date, time=time,
        version="VOSE", version_raw="VOSE", ticket_url=None, film_url=None, special=False, source="x",
    )


def ok(*sessions):
    return lambda cinema, http, today: list(sessions)


def boom(cinema, http, today):
    raise ConnectionError("timeout")


EMPTY = {"meta": {"sources": {}}, "sessions": []}


def test_clean_drops_past_invalid_and_duplicates():
    out = clean([
        _s(date="2026-10-28"),                 # pasada
        _s(time="24:30"),                      # hora imposible
        _s(), _s(title="PELI"),                # duplicada (sin distinguir mayúsculas)
        _s(time="12:00"),
    ], NOW.date())
    assert [(s.date, s.time) for s in out] == [("2026-10-30", "11:00"), ("2026-10-30", "12:00")]


def test_all_ok():
    doc = collect(CFG, NOW, EMPTY, {"src_a": ok(_s("a")), "src_b": ok(_s("b"), _s("b", date="2026-11-05"))})
    src = doc["meta"]["sources"]
    assert src["a"]["status"] == src["b"]["status"] == "ok"
    assert src["b"]["count"] == 2 and src["b"]["last_date"] == "2026-11-05"
    assert src["a"]["last_ok"] == doc["meta"]["generated_at"]
    assert len(doc["sessions"]) == 3


def test_failure_keeps_previous_sessions_as_stale():
    previous = collect(CFG, datetime(2026, 10, 28, 6, 17, tzinfo=MADRID), EMPTY, {
        "src_a": ok(_s("a")),
        "src_b": ok(_s("b", date="2026-10-28"), _s("b", date="2026-10-30")),
    })
    doc = collect(CFG, NOW, previous, {"src_a": ok(_s("a")), "src_b": boom})
    b = doc["meta"]["sources"]["b"]
    assert b["status"] == "error" and b["stale"] and "timeout" in b["message"]
    assert b["last_ok"] == "2026-10-28T06:17:00+01:00"
    # se conservan solo las futuras
    assert [(s["cinema_id"], s["date"]) for s in doc["sessions"]] == [("a", "2026-10-30"), ("b", "2026-10-30")]
    assert doc["meta"]["sources"]["a"]["status"] == "ok"


def test_stale_keeps_original_last_ok_across_failures():
    first = collect(CFG, datetime(2026, 10, 27, 6, 0, tzinfo=MADRID), EMPTY,
                    {"src_a": ok(_s("a")), "src_b": ok(_s("b"))})
    second = collect(CFG, datetime(2026, 10, 28, 6, 0, tzinfo=MADRID), first, {"src_a": ok(_s("a")), "src_b": boom})
    third = collect(CFG, NOW, second, {"src_a": ok(_s("a")), "src_b": boom})
    assert third["meta"]["sources"]["b"]["last_ok"] == "2026-10-27T06:00:00+01:00"


def test_zero_sessions_is_an_error():
    doc = collect(CFG, NOW, EMPTY, {"src_a": ok(_s("a")), "src_b": ok()})
    b = doc["meta"]["sources"]["b"]
    assert b["status"] == "error" and "0 sesiones" in b["message"]
    assert not b["stale"]  # no había nada que conservar


def test_build_filters_and_keeps_meta():
    data = collect(CFG, NOW, EMPTY, {
        "src_a": ok(_s("a", time="11:00"), _s("a", time="18:00"), _s("a", date="2026-10-31")),
        "src_b": boom,
    })
    doc = build(data, NOW, CFG)
    assert [(s["date"], s["time"]) for s in doc["sessions"]] == [("2026-10-30", "11:00")]
    assert doc["meta"]["sources"]["b"]["status"] == "error"
    assert doc["meta"]["filter"] == {"cutoff": "13:00", "weekdays": [0, 1, 2, 3, 4], "horizon_days": 14}
    assert doc["meta"]["built_at"] == NOW.isoformat()


@pytest.mark.parametrize("fails", [["src_a"], ["src_a", "src_b"]])
def test_main_exit_code(monkeypatch, tmp_path, fails):
    import scraper.run as run

    fetchers = {"src_a": ok(_s("a")), "src_b": ok(_s("b"))}
    for f in fails:
        fetchers[f] = boom
    monkeypatch.setattr(run, "load_config", lambda: CFG)
    monkeypatch.setattr(run, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(run, "_default_fetcher", lambda source: fetchers[source])
    assert run.main() == (1 if len(fails) == 2 else 0)
    assert (tmp_path / "sessions.json").exists()
