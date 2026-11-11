"""Métodos de análisis de series de atención. Funciones puras sobre pandas.Series con índice de fechas.

Cada método está documentado en docs/metodos.md. Resumen:

- Tendencia: pendiente de Theil-Sen sobre log(visitas mensuales) y prueba de Mann-Kendall
  (tau de Kendall frente al tiempo). "Sube" o "baja" si p < 0,05 y el cambio anual supera ±10 %.
- Picos: línea base = mediana móvil de los 56 días previos; dispersión = MAD de esos días.
  Un día es anómalo si su z robusto ≥ 6, triplica la línea base, la supera en ≥ 200 visitas y la
  línea base es de al menos 50 visitas diarias (excluye la creación de artículos).
  Los días anómalos cercanos (≤ 3 días) forman un evento.
- Vida media: días desde el máximo hasta que el exceso sobre la línea base cae a la mitad.
  Vuelta a la normalidad: días hasta que el exceso cae por debajo del 10 % durante 3 días seguidos.
- Estacionalidad: serie mensual dividida por su media móvil centrada de 12 meses; perfil por mes
  del año; fuerza = varianza explicada por el perfil; consistencia = correlación media entre años.
- Desfase: correlación cruzada de anomalías diarias (log menos mediana móvil de 28 días) para
  desfases de −30 a +30 días.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------- tendencia

TREND_MIN_MONTHS = 24
TREND_P = 0.05
TREND_MIN_ANNUAL = 0.10


def trend(monthly: pd.Series) -> dict | None:
    """Tendencia de largo plazo sobre la serie mensual. None si hay menos de 24 meses con datos."""
    s = monthly.dropna()
    s = s[s > 0]
    if len(s) < TREND_MIN_MONTHS:
        return None
    t_years = (s.index - s.index[0]).days.values / 365.25
    y = np.log(s.values.astype(float))
    slope, intercept, lo, hi = stats.theilslopes(y, t_years)
    tau, p = stats.kendalltau(t_years, y)
    annual = math.exp(slope) - 1
    if p < TREND_P and annual >= TREND_MIN_ANNUAL:
        label = "sube"
    elif p < TREND_P and annual <= -TREND_MIN_ANNUAL:
        label = "baja"
    else:
        label = "estable"
    return {
        "clase": label,
        "cambio_anual": round(annual, 4),
        "cambio_anual_ic95": [round(math.exp(lo) - 1, 4), round(math.exp(hi) - 1, 4)],
        "tau_kendall": round(float(tau), 3),
        "p_valor": float(p),
        "meses": int(len(s)),
        "desde": s.index[0].strftime("%Y-%m"),
        "hasta": s.index[-1].strftime("%Y-%m"),
    }


# ---------------------------------------------------------------- picos


@dataclass
class Peak:
    fecha: str
    inicio: str
    fin: str
    visitas: int
    linea_base: float
    magnitud: float  # visitas del día máximo / línea base
    exceso_total: int  # visitas sobre la línea base durante el evento hasta volver a la normalidad
    vida_media_dias: int | None
    vuelta_normalidad_dias: int | None
    z_robusto: float


def _baseline(daily: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    prev = daily.shift(1)
    med = prev.rolling(window, min_periods=window // 2).median()
    mad = (prev - med).abs().rolling(window, min_periods=window // 2).median()
    return med, mad


def detect_peaks(
    daily: pd.Series,
    *,
    window: int = 56,
    z_threshold: float = 6.0,
    min_ratio: float = 3.0,
    min_excess: float = 200.0,
    min_baseline: float = 50.0,
    gap_days: int = 3,
    max_follow: int = 365,
) -> list[Peak]:
    """Detecta picos de atención en una serie diaria (índice de fechas consecutivas)."""
    s = daily.astype(float).asfreq("D", fill_value=0.0)
    if len(s) < window + 7:
        return []
    med, mad = _baseline(s, window)
    scale = 1.4826 * mad
    scale = scale.where(scale > 0, np.maximum(1.0, 0.05 * med))
    z = (s - med) / scale
    # min_baseline: sin un nivel previo mínimo, la creación de un artículo (de 0 a cientos de visitas)
    # aparecería como un pico «infinito».
    flag = (z >= z_threshold) & (s >= min_ratio * med) & ((s - med) >= min_excess) & (med >= min_baseline) & med.notna()
    days = list(s.index[flag.fillna(False).values])
    if not days:
        return []

    # Agrupa días anómalos cercanos en eventos.
    groups: list[list[pd.Timestamp]] = [[days[0]]]
    for d in days[1:]:
        if (d - groups[-1][-1]).days <= gap_days:
            groups[-1].append(d)
        else:
            groups.append([d])

    values = s.values
    idx = {d: i for i, d in enumerate(s.index)}
    peaks: list[Peak] = []
    for g in groups:
        start_i = idx[g[0]]
        base = float(med.iloc[start_i])  # línea base previa al evento, fija
        peak_i = max(range(start_i, idx[g[-1]] + 1), key=lambda i: values[i])
        peak_v = float(values[peak_i])
        excess_peak = peak_v - base
        half = None
        back = None
        streak = 0
        excess_sum = 0.0
        for j in range(peak_i, min(len(values), peak_i + max_follow + 1)):
            ex = values[j] - base
            if half is None and ex <= 0.5 * excess_peak:
                half = j - peak_i
            if ex <= 0.1 * excess_peak:
                streak += 1
                if streak == 3:
                    back = j - 2 - peak_i
                    break
            else:
                streak = 0
                excess_sum += max(ex, 0)
        for j in range(start_i, peak_i):
            excess_sum += max(values[j] - base, 0)
        end_i = peak_i + back if back is not None else idx[g[-1]]
        peaks.append(
            Peak(
                fecha=s.index[peak_i].strftime("%Y-%m-%d"),
                inicio=g[0].strftime("%Y-%m-%d"),
                fin=s.index[min(end_i, len(s) - 1)].strftime("%Y-%m-%d"),
                visitas=int(peak_v),
                linea_base=round(base, 1),
                magnitud=round(peak_v / max(base, 1.0), 2),
                exceso_total=int(excess_sum),
                vida_media_dias=half,
                vuelta_normalidad_dias=back,
                z_robusto=round(float(z.iloc[peak_i]), 1),
            )
        )

    # Si un evento empieza antes de que el anterior vuelva a la normalidad, se fusionan (quedando el mayor).
    merged: list[Peak] = []
    for p in peaks:
        if merged and p.inicio <= merged[-1].fin:
            if p.visitas > merged[-1].visitas:
                merged[-1] = p
            continue
        merged.append(p)
    return merged


def peaks_as_dicts(peaks: list[Peak], top: int | None = None) -> list[dict]:
    ordered = sorted(peaks, key=lambda p: p.magnitud, reverse=True)
    if top:
        ordered = ordered[:top]
    return [asdict(p) for p in ordered]


# ---------------------------------------------------------------- estacionalidad


def seasonality(monthly: pd.Series) -> dict | None:
    """Perfil estacional por mes del año. None si hay menos de 3 años completos."""
    s = monthly.dropna().astype(float)
    s = s[s > 0]
    if len(s) < 48:
        return None
    logs = np.log(s)
    trend_ = logs.rolling(12, center=True, min_periods=12).mean()
    # Media móvil centrada de 12 meses (2x12) para un número par de periodos.
    trend_ = trend_.rolling(2, min_periods=2).mean().shift(-1)
    detr = (logs - trend_).dropna()
    if len(detr) < 36:
        return None
    month = detr.index.month
    profile = detr.groupby(month).mean()
    if len(profile) < 12:
        return None
    fitted = profile.reindex(month).values
    var = float(np.var(detr.values))
    strength = 1 - float(np.var(detr.values - fitted)) / var if var > 0 else 0.0

    # Consistencia: correlación media entre los perfiles de cada año completo.
    years = []
    for _, g in detr.groupby(detr.index.year):
        if len(g) == 12:
            years.append(g.values)
    corrs = []
    for i in range(len(years)):
        for j in range(i + 1, len(years)):
            r = stats.pearsonr(years[i], years[j]).statistic
            if not np.isnan(r):
                corrs.append(r)
    consistency = float(np.mean(corrs)) if corrs else None
    is_seasonal = strength >= 0.3 and (consistency or 0) >= 0.4
    factor = np.exp(profile)  # 1.2 = 20 % por encima de lo normal para ese año
    return {
        "estacional": bool(is_seasonal),
        "fuerza": round(strength, 3),
        "consistencia": None if consistency is None else round(consistency, 3),
        "anios_completos": len(years),
        "perfil": [round(float(factor.get(m, np.nan)), 4) for m in range(1, 13)],
        "mes_pico": int(profile.idxmax()),
        "mes_valle": int(profile.idxmin()),
    }


# ---------------------------------------------------------------- comparación entre series


def anomalies(daily: pd.Series, window: int = 28) -> pd.Series:
    """log(1+visitas) menos su mediana móvil centrada: deja solo las subidas y bajadas de corto plazo."""
    lg = np.log1p(daily.astype(float))
    return (lg - lg.rolling(window, center=True, min_periods=window // 2).median()).dropna()


def lagged_correlation(a: pd.Series, b: pd.Series, max_lag: int = 30) -> dict | None:
    """Correlación cruzada de anomalías diarias.

    desfase > 0 significa que `b` va DETRÁS de `a` (el interés en b llega `desfase` días después).
    """
    xa, xb = anomalies(a), anomalies(b)
    common = xa.index.intersection(xb.index)
    if len(common) < 365:
        return None
    xa, xb = xa.loc[common], xb.loc[common]
    best_lag, best_r = 0, -2.0
    by_lag = {}
    for lag in range(-max_lag, max_lag + 1):
        r = xa.corr(xb.shift(-lag))
        by_lag[lag] = r
        if r is not None and not np.isnan(r) and r > best_r:
            best_lag, best_r = lag, r
    r0 = by_lag[0]
    return {
        "desfase_dias": int(best_lag),
        "r_max": round(float(best_r), 3),
        "r_0": round(float(r0), 3),
        "dias": int(len(common)),
        # Un desfase solo se considera informativo si la correlación es clara y mejora a la de lag 0.
        "informativo": bool(best_r >= 0.3 and best_lag != 0 and best_r - r0 >= 0.02),
    }


def monthly_log_corr(a: pd.Series, b: pd.Series) -> float | None:
    common = a.dropna().index.intersection(b.dropna().index)
    if len(common) < 24:
        return None
    x, y = np.log1p(a.loc[common].astype(float)), np.log1p(b.loc[common].astype(float))
    r = x.corr(y)
    return None if np.isnan(r) else round(float(r), 3)


def weekly_anomalies(daily: pd.Series) -> pd.Series:
    """log(visitas semanales) menos su mediana móvil centrada de 13 semanas."""
    w = np.log1p(daily.resample("W").sum())
    return (w - w.rolling(13, center=True, min_periods=7).median()).dropna()


def remove_common_factor(anoms: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Resta a cada tema la anomalía media de todos los temas esa semana.

    Sin esto, los cambios que afectan a todo Wikipedia (olas de tráfico automatizado, caídas por
    cambios en buscadores, fiestas) hacen que casi cualquier par de temas parezca «moverse junto».
    """
    df = pd.DataFrame(anoms)
    common = df.mean(axis=1)
    return {k: (df[k] - common).dropna() for k in df.columns}


def weekly_anomaly_corr(a: pd.Series, b: pd.Series, *, already_anomalies: bool = False) -> tuple[float, float, int] | None:
    """Correlación de anomalías semanales (sin tendencia). Devuelve (r, p, n)."""
    da = a if already_anomalies else weekly_anomalies(a)
    db = b if already_anomalies else weekly_anomalies(b)
    common = da.dropna().index.intersection(db.dropna().index)
    if len(common) < 104:
        return None
    r, p = stats.pearsonr(da.loc[common], db.loc[common])
    return round(float(r), 3), float(p), int(len(common))
