"""Arma el sitio estático para GitHub Pages / Cloudflare Pages.

Requiere la web compilada en modo estático:  VITE_STATIC=1 VITE_BASE=/<repo>/ npm --prefix web run build
Resultado: <out>/ con la web, <out>/data/ (exportación JSON) y <out>/reporte.html.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .settings import PATHS


def build_site(out: str | Path = "site") -> Path:
    out = Path(out)
    if not out.is_absolute():
        out = PATHS.root / out
    dist = PATHS.root / "web" / "dist"
    if not (dist / "index.html").exists():
        raise SystemExit("Falta web/dist. Compila antes con: VITE_STATIC=1 npm --prefix web run build")
    if not (PATHS.web / "meta.json").exists():
        raise SystemExit("Falta la exportación. Ejecuta antes: python -m observatorio export")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(dist, out)
    shutil.copytree(PATHS.web, out / "data")
    report = PATHS.reports / "observatorio.html"
    if report.exists():
        shutil.copy(report, out / "reporte.html")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: servir tal cual, sin Jekyll
    return out
