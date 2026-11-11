"""Cálculo de la próxima ejecución del programador diario usado en Docker."""

import datetime as dt
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("programador", Path(__file__).resolve().parents[1] / "scripts" / "programador.py")
programador = importlib.util.module_from_spec(spec)
spec.loader.exec_module(programador)

TZ = ZoneInfo("America/Santiago")


def test_same_day_if_hour_not_reached():
    now = dt.datetime(2026, 11, 11, 7, 30, tzinfo=TZ)
    assert programador.next_run(now, "09:00") == dt.datetime(2026, 11, 11, 9, 0, tzinfo=TZ)


def test_next_day_if_hour_passed():
    now = dt.datetime(2026, 11, 11, 9, 0, 1, tzinfo=TZ)
    assert programador.next_run(now, "09:00") == dt.datetime(2026, 11, 12, 9, 0, tzinfo=TZ)
