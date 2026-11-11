"""Detección de picos, vida media, tendencia, estacionalidad y desfases."""

import numpy as np
import pandas as pd

from observatorio.analysis import timeseries as T


def _series(n=900, level=1000.0, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(level * rng.lognormal(0, 0.05, n), index=idx)


def test_detects_single_peak_with_known_half_life():
    s = _series()
    peak_day, mult, half = 400, 30.0, 4.0
    k = np.arange(len(s)) - peak_day
    s = s + np.where(k >= 0, 1000 * mult * 0.5 ** (np.clip(k, 0, None) / half), 0)
    peaks = T.detect_peaks(s)
    assert len(peaks) == 1
    p = peaks[0]
    assert p.fecha == s.index[peak_day].strftime("%Y-%m-%d")
    assert 25 < p.magnitud < 36  # (1000 + 30000) / ~1000
    assert p.vida_media_dias == 4  # exceso cae a la mitad en ~4 días
    # 10 % del exceso: 4 * log2(10) ≈ 13,3 días
    assert 12 <= p.vuelta_normalidad_dias <= 15


def test_no_peaks_in_noise():
    assert T.detect_peaks(_series(seed=3)) == []


def test_small_absolute_spikes_ignored():
    s = _series(level=10)
    s.iloc[500] = 200  # 20× pero solo 190 visitas sobre la base
    assert T.detect_peaks(s) == []


def test_peak_that_never_recovers():
    s = _series()
    s.iloc[600:] = s.iloc[600:] + 20000  # cambio de nivel permanente
    p = T.detect_peaks(s)[0]
    assert p.vuelta_normalidad_dias is None


def test_trend_up_down_flat():
    idx = pd.date_range("2016-01-01", periods=96, freq="MS")
    rng = np.random.default_rng(1)
    noise = rng.lognormal(0, 0.03, 96)
    up = pd.Series(1000 * 1.3 ** (np.arange(96) / 12) * noise, index=idx)
    down = pd.Series(1000 * 0.7 ** (np.arange(96) / 12) * noise, index=idx)
    flat = pd.Series(1000 * noise, index=idx)
    assert T.trend(up)["clase"] == "sube" and abs(T.trend(up)["cambio_anual"] - 0.3) < 0.03
    assert T.trend(down)["clase"] == "baja"
    assert T.trend(flat)["clase"] == "estable"
    assert T.trend(up.iloc[:10]) is None


def test_seasonality_detects_month():
    idx = pd.date_range("2016-01-01", periods=96, freq="MS")
    rng = np.random.default_rng(2)
    prof = 1 + 0.5 * (idx.month == 12)
    s = pd.Series(1000 * prof * rng.lognormal(0, 0.02, 96), index=idx)
    out = T.seasonality(s)
    assert out["estacional"] and out["mes_pico"] == 12
    flat = T.seasonality(pd.Series(1000 * rng.lognormal(0, 0.05, 96), index=idx))
    assert not flat["estacional"]


def test_lag_detection_sign_convention():
    rng = np.random.default_rng(5)
    idx = pd.date_range("2019-01-01", periods=1200, freq="D")
    shocks = np.zeros(1200)
    shocks[rng.choice(1100, 40, replace=False)] = rng.uniform(2, 10, 40)
    a_exc = np.convolve(shocks, 0.7 ** np.arange(20))[:1200]
    a = pd.Series(1000 * (1 + a_exc) * rng.lognormal(0, 0.05, 1200), index=idx)
    b_exc = np.roll(a_exc, 5)  # b llega 5 días después
    b = pd.Series(500 * (1 + b_exc) * rng.lognormal(0, 0.05, 1200), index=idx)
    res = T.lagged_correlation(a, b)
    assert res["desfase_dias"] == 5
    assert res["informativo"]
    res_rev = T.lagged_correlation(b, a)
    assert res_rev["desfase_dias"] == -5


def test_lag_requires_enough_overlap():
    s = _series(n=200)
    assert T.lagged_correlation(s, s) is None
