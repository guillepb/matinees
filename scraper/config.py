"""Carga de config.yaml."""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("timezone", "Europe/Madrid")
    cfg.setdefault("matinee", {})
    cfg["matinee"].setdefault("cutoff", "13:00")
    cfg["matinee"].setdefault("weekdays", [0, 1, 2, 3, 4])
    cfg["matinee"].setdefault("horizon_days", 14)
    cfg.setdefault("cinemas", [])
    return cfg


def tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg["timezone"])
