"""CLI: python -m observatorio {fetch,analyze,report,export,all}."""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="observatorio", description="Observatorio de la Curiosidad")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="descarga datos de Wikimedia (con caché)")
    f.add_argument("--topics", nargs="*", help="ids de temas (por defecto, todos)")
    g = f.add_mutually_exclusive_group()
    g.add_argument("--skip-countries", action="store_true", help="no descargar rankings por país")
    g.add_argument("--countries-only", action="store_true", help="solo rankings por país")

    sub.add_parser("analyze", help="calcula tendencias, picos, estacionalidad, desfases y grupos")
    sub.add_parser("report", help="genera reports/observatorio.html")
    sub.add_parser("export", help="genera los agregados JSON que usa la web/API")
    a = sub.add_parser("all", help="fetch + analyze + report + export")
    a.add_argument("--skip-countries", action="store_true")
    sub.add_parser("demo", help="genera datos SINTÉTICOS marcados como tales (para probar sin conexión)")
    st = sub.add_parser("site", help="arma el sitio estático (web compilada con VITE_STATIC=1 + datos + reporte)")
    st.add_argument("--out", default="site", help="carpeta de salida (por defecto: site)")
    sub.add_parser("disputa", help="descarga y calcula «Bajo disputa» (ediciones revertidas de la última semana)")
    sub.add_parser("daily", help="actualización diaria: descarga solo lo nuevo, recalcula y genera las curiosidades del día")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.cmd == "demo":
        from .demo import generate

        generate()
        print("Datos SINTÉTICOS generados en data/processed (marcados con DEMO). Ejecuta analyze, report y export.")
        return 0
    if args.cmd == "site":
        from .site import build_site

        print(f"Sitio estático: {build_site(args.out)}")
        return 0
    if args.cmd == "disputa":
        from .pipeline import fetch_disputes_to_disk

        fetch_disputes_to_disk()
        return 0
    if args.cmd == "daily":
        from .pipeline import daily
        from .settings import MissingContactError

        try:
            daily()
        except (MissingContactError, PermissionError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.cmd in ("fetch", "all"):
        from .pipeline import fetch
        from .settings import MissingContactError

        try:
            fetch(
                getattr(args, "topics", None) or None,
                pageviews=not getattr(args, "countries_only", False),
                countries=not args.skip_countries,
            )
        except (MissingContactError, PermissionError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    if args.cmd in ("analyze", "all"):
        from .analysis.run import analyze

        analyze()
    if args.cmd in ("report", "all"):
        from .report.build import build_report

        path = build_report()
        print(f"Reporte: {path}")
    if args.cmd in ("export", "all"):
        from .export import export

        export()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
