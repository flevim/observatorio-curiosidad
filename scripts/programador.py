"""Programador de la actualización diaria para Docker (reemplaza al Programador de tareas de Windows).

Ejecuta `python -m observatorio daily` todos los días a la hora OBSERVATORIO_HORA_DIARIA (HH:MM, zona horaria TZ).
Con OBSERVATORIO_EJECUTAR_AL_INICIAR=1 también ejecuta una vez al arrancar.
El registro queda en data/daily.log y en `docker compose logs actualizador`.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("OBSERVATORIO_ROOT", Path(__file__).resolve().parents[1]))
LOG = ROOT / "data" / "daily.log"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def next_run(now: dt.datetime, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return target if target > now else target + dt.timedelta(days=1)


def run_daily() -> int:
    log("Inicio de la actualización diaria")
    proc = subprocess.run([sys.executable, "-m", "observatorio", "daily"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        for line in (proc.stdout + proc.stderr).splitlines():
            if not line.startswith(("visitas: ", "rankings: ")):
                f.write(line + "\n")
    log(f"Fin (código {proc.returncode})")
    return proc.returncode


def main() -> None:
    tz = ZoneInfo(os.environ.get("TZ", "UTC"))
    hhmm = os.environ.get("OBSERVATORIO_HORA_DIARIA", "09:00")
    log(f"Programador iniciado: todos los días a las {hhmm} ({tz.key})")
    if os.environ.get("OBSERVATORIO_EJECUTAR_AL_INICIAR") == "1":
        run_daily()
    while True:
        now = dt.datetime.now(tz)
        target = next_run(now, hhmm)
        log(f"Próxima ejecución: {target.strftime('%Y-%m-%d %H:%M %Z')}")
        # Dormir en tramos cortos para tolerar suspensiones del equipo y cambios de hora.
        while (remaining := (target - dt.datetime.now(tz)).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        run_daily()


if __name__ == "__main__":
    main()
