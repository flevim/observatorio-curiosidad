"""Hallazgos redactados en español a partir de números calculados.

Regla: cada frase sale de una métrica concreta y la cita. Si los datos no muestran algo, no se dice.
No se atribuyen causas a los picos: solo se dan fechas y magnitudes.
"""

from __future__ import annotations

import numpy as np

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
IDIOMAS = {
    "es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "de": "alemán", "ja": "japonés",
    "it": "italiano", "ru": "ruso", "zh": "chino", "ar": "árabe", "todas": "todos los idiomas",
}
ALL = "todas"


def pl(n: int, uno: str, varios: str) -> str:
    """Concordancia: pl(1, "tema sube", "temas suben") -> "1 tema sube"."""
    return f"{n} {uno if n == 1 else varios}"


def num(x: float, dec: int = 0) -> str:
    """Formato numérico en español: 12.345,6"""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x: float, dec: int = 0) -> str:
    return f"{num(x * 100, dec)} %"


def fecha(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]} de {y}"


def lang(code: str) -> str:
    return IDIOMAS.get(code, code)


def build_findings(topics: dict, sem: list, stat: list, clusters: dict, context: dict) -> dict:
    H: list[dict] = []  # todos los hallazgos
    S: list[tuple[float, dict]] = []  # candidatos a "sorprendentes" con puntuación

    def add(key, titulo, texto, temas, numeros, sorpresa=None):
        h = {"id": key, "titulo": titulo, "texto": texto, "temas": temas, "numeros": numeros}
        H.append(h)
        if sorpresa is not None:
            S.append((sorpresa, h))

    name = {t: v["nombre"] for t, v in topics.items()}

    # --- Tendencias
    trends = [(t, v["por_idioma"][ALL]["tendencia"]) for t, v in topics.items() if ALL in v["por_idioma"] and v["por_idioma"][ALL]["tendencia"]]
    ups = sorted([x for x in trends if x[1]["clase"] == "sube"], key=lambda x: -x[1]["cambio_anual"])
    downs = sorted([x for x in trends if x[1]["clase"] == "baja"], key=lambda x: x[1]["cambio_anual"])
    flat = [x for x in trends if x[1]["clase"] == "estable"]
    if trends:
        add(
            "tendencias-resumen",
            "Cuántos temas suben, bajan o se mantienen",
            f"Sumando los idiomas analizados, {len(ups)} de {len(trends)} temas {'tiene' if len(ups) == 1 else 'tienen'} tendencia al alza, {len(downs)} a la baja "
            f"y {len(flat)} no {'muestra' if len(flat) == 1 else 'muestran'} un cambio significativo (Theil-Sen sobre el logaritmo de las visitas mensuales; "
            f"significativo si p < 0,05 en Mann-Kendall y el cambio supera el 10 % anual).",
            [t for t, _ in trends],
            {"sube": len(ups), "baja": len(downs), "estable": len(flat)},
        )
    rel = [(t, v["por_idioma"][ALL].get("tendencia_relativa")) for t, v in topics.items() if ALL in v["por_idioma"]]
    rel = [(t, r) for t, r in rel if r]
    if rel:
        rup = sorted([x for x in rel if x[1]["clase"] == "sube"], key=lambda x: -x[1]["cambio_anual"])
        rdown = [x for x in rel if x[1]["clase"] == "baja"]
        txt = (f"Como Wikipedia en conjunto también cambió de tamaño, se repitió el cálculo con la proporción del tema sobre "
               f"todas las visitas de sus ediciones: {pl(len(rup), 'tema sube', 'temas suben')}, {pl(len(rdown), 'baja', 'bajan')} y "
               f"{pl(len(rel) - len(rup) - len(rdown), 'se mantiene', 'se mantienen')} en términos relativos.")
        moved = [name[t] for t, r in rel if r["clase"] != next((x[1]["clase"] for x in trends if x[0] == t), r["clase"])]
        if moved:
            txt += f" Cambian de clase al medirlos así: {', '.join(sorted(moved))}."
        add("tendencia-relativa", "Tendencias descontando el cambio de Wikipedia", txt, [t for t, _ in rup],
            {"sube": len(rup), "baja": len(rdown)})
    if ups:
        t, tr = ups[0]
        add(
            "mayor-subida",
            f"{name[t]}: la mayor subida sostenida",
            f"La atención a «{name[t]}» crece en promedio {pct(tr['cambio_anual'])} por año entre {tr['desde']} y {tr['hasta']} "
            f"(intervalo de confianza 95 %: {pct(tr['cambio_anual_ic95'][0])} a {pct(tr['cambio_anual_ic95'][1])}).",
            [t], tr, sorpresa=min(tr["cambio_anual"], 3) * 0.5,
        )
    if downs:
        t, tr = downs[0]
        add(
            "mayor-bajada",
            f"{name[t]}: la mayor caída sostenida",
            f"Las visitas a «{name[t]}» bajan en promedio {pct(-tr['cambio_anual'])} por año entre {tr['desde']} y {tr['hasta']}. "
            "Parte de la caída general de Wikipedia puede deberse a cambios en cómo se busca información "
            "(respuestas directas en buscadores y asistentes), no necesariamente a menor interés.",
            [t], tr,
        )

    # --- Picos y vida media
    best = None
    for t, v in topics.items():
        for lg, m in v["por_idioma"].items():
            if lg == ALL:
                continue
            for p in m["picos"]:
                if best is None or p["magnitud"] > best[2]["magnitud"]:
                    best = (t, lg, p)
    if best:
        t, lg, p = best
        hl = f"; la atención se redujo a la mitad en {p['vida_media_dias']} días" if p["vida_media_dias"] is not None else ""
        back = (f" y volvió a lo normal en {p['vuelta_normalidad_dias']} días" if p["vuelta_normalidad_dias"] is not None
                else " y no volvió a su nivel previo dentro del año siguiente")
        add(
            "mayor-pico",
            f"El pico más abrupto: {name[t]} en {lang(lg)}",
            f"El {fecha(p['fecha'])}, «{name[t]}» en Wikipedia en {lang(lg)} recibió {num(p['visitas'])} visitas, "
            f"{num(p['magnitud'], 1)} veces su nivel habitual de {num(p['linea_base'])} visitas diarias{hl}{back}. "
            "El dato muestra el salto, no su causa.",
            [t], {"idioma": lg, **p}, sorpresa=np.log10(max(p["magnitud"], 1)),
        )

    halves = []
    for t, v in topics.items():
        m = v["por_idioma"].get(ALL)
        if m and m["vida_media_mediana"] is not None and m["n_picos"] >= 2:
            halves.append((t, m["vida_media_mediana"], m["n_picos"]))
    if len(halves) >= 3:
        halves.sort(key=lambda x: x[1])
        fast, slow = halves[0], halves[-1]
        add(
            "vida-media",
            "Atención fugaz frente a atención duradera",
            f"Tras un pico, el interés en «{name[fast[0]]}» se reduce a la mitad en una mediana de {num(fast[1], 1)} días "
            f"({fast[2]} picos), mientras que en «{name[slow[0]]}» tarda {num(slow[1], 1)} días ({slow[2]} picos). "
            f"La mediana entre los {len(halves)} temas con al menos dos picos es {num(float(np.median([h[1] for h in halves])), 1)} días.",
            [fast[0], slow[0]], {"rapido": fast, "lento": slow},
            sorpresa=0.6 if slow[1] >= 3 * max(fast[1], 0.5) else None,
        )

    # --- Estacionalidad
    seas = [(t, v["por_idioma"][ALL]["estacionalidad"]) for t, v in topics.items()
            if ALL in v["por_idioma"] and v["por_idioma"][ALL]["estacionalidad"]]
    seasonal = sorted([x for x in seas if x[1]["estacional"]], key=lambda x: -x[1]["fuerza"])
    if seas:
        if seasonal:
            t, s = seasonal[0]
            hi, lo = max(s["perfil"]), min(s["perfil"])
            add(
                "estacionalidad",
                f"{name[t]}: el tema más estacional",
                f"{len(seasonal)} de {len(seas)} temas muestran un patrón anual que se repite. El más marcado es «{name[t]}»: "
                f"el perfil mensual explica el {pct(s['fuerza'])} de la variación sin tendencia, con máximo en {MESES[s['mes_pico'] - 1]} "
                f"({pct(hi - 1)} sobre lo normal) y mínimo en {MESES[s['mes_valle'] - 1]} ({pct(1 - lo)} por debajo). "
                f"La correlación media entre años es {num(s['consistencia'], 2)}.",
                [x[0] for x in seasonal], {"tema": t, **s}, sorpresa=s["fuerza"],
            )
        else:
            add("estacionalidad", "Poca estacionalidad", "Ningún tema supera el umbral de estacionalidad (fuerza ≥ 0,3 y consistencia ≥ 0,4).", [], {})

    # --- Desfase español / inglés
    es_lags = []
    for t, v in topics.items():
        for c in v["comparacion_idiomas"]:
            if c["idioma"] == "es" and c["desfase"]:
                es_lags.append((t, c["desfase"]))
    if es_lags:
        informative = [(t, d) for t, d in es_lags if d["informativo"]]
        same_day = sum(1 for _, d in es_lags if d["desfase_dias"] == 0)
        txt = (f"En {same_day} de {len(es_lags)} temas, las subidas y bajadas diarias en español e inglés coinciden mejor el mismo día "
               f"(correlación de anomalías diarias, desfases de −30 a +30 días).")
        if informative:
            informative.sort(key=lambda x: -abs(x[1]["desfase_dias"]))
            t, d = informative[0]
            dirn = "después" if d["desfase_dias"] > 0 else "antes"
            txt += (f" La excepción más clara es «{name[t]}»: el interés en español llega {abs(d['desfase_dias'])} días {dirn} que en inglés "
                    f"(r = {num(d['r_max'], 2)} frente a {num(d['r_0'], 2)} el mismo día).")
        add("desfase-es-en", "¿El español va detrás del inglés?", txt, [t for t, _ in informative],
            {"mismo_dia": same_day, "total": len(es_lags), "informativos": len(informative)},
            sorpresa=0.5 if informative and abs(informative[0][1]["desfase_dias"]) >= 3 else None)

    # --- Peso relativo por idioma
    bestw = None
    for t, v in topics.items():
        for lg, w in (v.get("peso_relativo") or {}).items():
            if bestw is None or w["indice"] > bestw[2]["indice"]:
                bestw = (t, lg, w)
    if bestw and bestw[2]["indice"] < 1.5:
        t, lg, w = bestw
        add("peso-idioma", "Pesos parecidos entre idiomas",
            f"Ningún tema pesa 1,5 veces o más en un idioma que en el promedio; el máximo es «{name[t]}» en {lang(lg)} "
            f"({num(w['indice'], 2)} veces).", [t], {"idioma": lg, **w})
    elif bestw:
        t, lg, w = bestw
        add(
            "peso-idioma",
            f"«{name[t]}» pesa mucho más en {lang(lg)}",
            f"En los últimos 12 meses, «{name[t]}» concentra {num(w['proporcion_por_millon'], 1)} de cada millón de visitas de "
            f"Wikipedia en {lang(lg)}: {num(w['indice'], 1)} veces la proporción media de los idiomas analizados. "
            "Esto describe a quienes leen en ese idioma, no a un país.",
            [t], {"idioma": lg, **w}, sorpresa=np.log2(max(w["indice"], 1)) / 2,
        )

    # --- Relaciones estadísticas sin vínculo semántico
    sem_pairs = {(r["a"], r["b"]) for r in sem}
    surprising = sorted([r for r in stat if (r["a"], r["b"]) not in sem_pairs], key=lambda r: -r["r"])
    if stat:
        txt = f"{len(stat)} pares de temas suben y bajan juntos semana a semana (anomalías sin tendencia, r ≥ {num(0.25, 2)}, p ≤ 0,001)."
        if surprising:
            r = surprising[0]
            txt += (f" El par más fuerte sin vínculo en Wikipedia ni en Wikidata es «{name[r['a']]}» y «{name[r['b']]}» "
                    f"(r = {num(r['r'], 2)}, {r['semanas']} semanas). Que se muevan juntos no implica que uno cause al otro.")
        add("co-movimiento", "Temas que se mueven juntos", txt, [surprising[0]["a"], surprising[0]["b"]] if surprising else [],
            {"pares": len(stat), "sin_vinculo": len(surprising)}, sorpresa=surprising[0]["r"] if surprising else None)

    # --- Rankings por país (aproximados)
    pres = [(t, v["paises"]) for t, v in topics.items() if v.get("paises")]
    if pres:
        wide = max(pres, key=lambda x: x[1]["paises"])
        steady = max(pres, key=lambda x: x[1]["meses_con_presencia"])
        never = sorted(name[t] for t, v in topics.items() if not v.get("paises"))
        txt = (f"En los rankings diarios de artículos más vistos por país (días muestreados desde 2021, cifras aproximadas), "
               f"«{name[wide[0]]}» es el tema que apareció en más países ({wide[1]['paises']}), y «{name[steady[0]]}» el más constante "
               f"({steady[1]['meses_con_presencia']} meses con presencia; mejor puesto {steady[1]['top_paises'][0]['mejor_puesto']} en "
               f"{steady[1]['top_paises'][0]['pais']}).")
        if never:
            txt += f" Nunca entraron en un ranking: {', '.join(never)}. Eso no es cero interés: solo entran artículos con muchas visitas diarias en un país."
        add("rankings-paises", "Qué temas llegan a los rankings por país", txt, [wide[0], steady[0]] if wide[0] != steady[0] else [wide[0]],
            {"tema": wide[0], "paises": wide[1]["paises"]}, sorpresa=0.4)

    # --- Grupos
    if clusters.get("grupos"):
        parts = [f"{{{', '.join(g['nombres'])}}}" for g in clusters["grupos"]]
        add("grupos", "Familias de temas con trayectorias parecidas",
            f"El agrupamiento jerárquico separa los temas en {clusters['k']} grupos (silueta {num(clusters['silueta'], 2)}): " + "; ".join(parts) + ".",
            [], {"k": clusters["k"], "silueta": clusters["silueta"]})

    # --- Contexto: móvil
    ms = context.get("proporcion_movil", {}).get("en", {})
    years = sorted(int(y) for y in ms)
    if len(years) >= 3:
        y0, y1 = years[0] + 1 if years[0] == 2015 else years[0], years[-1] - 1 if len(years) > 3 else years[-1]
        if str(y0) in map(str, ms) and str(y1) in map(str, ms):
            add("movil", "El tráfico cambió de pantalla",
                f"En Wikipedia en inglés, la proporción de visitas desde móviles pasó de {pct(ms[y0])} en {y0} a {pct(ms[y1])} en {y1}. "
                "Comparar épocas implica comparar públicos y formas de acceso distintas.",
                [], {"desde": [y0, ms[y0]], "hasta": [y1, ms[y1]]})

    sorpr = [h for _, h in sorted(S, key=lambda x: -x[0])[:5]]
    return {"hallazgos": H, "sorprendentes": sorpr}
