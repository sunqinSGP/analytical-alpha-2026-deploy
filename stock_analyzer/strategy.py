"""
Systematic-strategy signals — equity factor scores (value / momentum / quality / low-vol),
a cross-sectional MULTI-FACTOR ranking, and TREND / market-REGIME signals.

Pure maths (no network, no Streamlit), unit-tested offline. Evidence + honest caveats live in
docs/strategy_research.md. Key principles baked in from the research:
  - Use FIXED strategic factor weights, not factor timing (Asness, 'The Siren Song of Factor Timing').
  - Historical factor edge decays ~26% out-of-sample / ~58% post-publication (McLean-Pontiff, JF 2016)
    — treat composite ranks as a tilt, not a guarantee; the UI applies a plain-language haircut note.
  - TREND-following is a convex, long-volatility 'crisis-alpha' COMPLEMENT to option-selling
    (concave, short-vol), not a replacement.
Everything here is informational, not financial advice.
"""
import math

DEFAULT_FACTOR_WEIGHTS = {'value': 1.0, 'momentum': 1.0, 'quality': 1.0, 'lowvol': 1.0}
FACTORS = ('value', 'momentum', 'quality', 'lowvol')
FACTOR_LABELS = {'value': 'Value', 'momentum': 'Momentum', 'quality': 'Quality', 'lowvol': 'Low-vol'}


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-stock raw factor signals (each ORIENTED so HIGHER = better; None if N/A)
# ---------------------------------------------------------------------------
def value_raw(info):
    """Cheapness = earnings yield + free-cash-flow yield (higher = cheaper = better)."""
    if not info:
        return None
    pe = _f(info.get('trailingPE')) or _f(info.get('forwardPE'))
    ey = (1.0 / pe) if pe and pe > 0 else None
    mcap, fcf = _f(info.get('marketCap')), _f(info.get('freeCashflow'))
    fcfy = (fcf / mcap) if (mcap and mcap > 0 and fcf is not None) else None
    vals = [v for v in (ey, fcfy) if v is not None]
    return sum(vals) if vals else None


def momentum_12_1(closes):
    """12-1 month price momentum: return from ~12 months ago to ~1 month ago (skip the last month)."""
    if not closes or len(closes) < 240:
        return None
    a = closes[-252] if len(closes) >= 252 else closes[0]
    b = closes[-21]
    if not a or a <= 0 or not b or b <= 0:
        return None
    return b / a - 1.0


def realized_vol(closes, window=252):
    """Annualised realised volatility from daily closes (last `window` returns)."""
    rets = []
    for i in range(1, len(closes)):
        x, y = closes[i - 1], closes[i]
        if x and y and x > 0 and y > 0:
            rets.append(math.log(y / x))
    rets = rets[-window:]
    if len(rets) < 20:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * 252)


def quality_raw(info):
    """Profitability/health = ROE + profit margin, minus a mild leverage penalty (higher = better)."""
    if not info:
        return None
    roe, pm, de = _f(info.get('returnOnEquity')), _f(info.get('profitMargins')), _f(info.get('debtToEquity'))
    parts = [v for v in (roe, pm) if v is not None]
    if not parts:
        return None
    q = sum(parts)
    if de is not None:
        q -= (de / 100.0) * 0.25            # debtToEquity is a percent (~50 => 0.5x); mild penalty
    return q


def lowvol_raw(closes):
    """Low-volatility factor = negative realised vol (calmer stock => higher score)."""
    v = realized_vol(closes)
    return (-v) if v is not None else None


def stock_factor_raw(info, closes):
    """All four raw factor signals for one stock (each higher=better, or None)."""
    return {'value': value_raw(info), 'momentum': momentum_12_1(closes),
            'quality': quality_raw(info), 'lowvol': lowvol_raw(closes)}


# ---------------------------------------------------------------------------
# Cross-sectional z-score + composite multi-factor ranking
# ---------------------------------------------------------------------------
def zscores(values):
    """Z-score a list across the cross-section (None stays None). Population stdev of present values."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return [0.0 if v is not None else None for v in values]
    m = sum(present) / len(present)
    sd = math.sqrt(sum((v - m) ** 2 for v in present) / len(present)) or 1.0
    return [((v - m) / sd if v is not None else None) for v in values]


def rank_universe(stocks, weights=None):
    """stocks: list of dicts each with a 'factors' sub-dict (from stock_factor_raw). Z-scores each
    factor across the universe, weight-averages the present z-scores into a composite, and returns
    the list sorted by composite (desc) with per-factor z-scores ('z') and 'composite' added."""
    weights = {**DEFAULT_FACTOR_WEIGHTS, **(weights or {})}
    z = {fac: zscores([(s.get('factors') or {}).get(fac) for s in stocks]) for fac in FACTORS}
    out = []
    for i, s in enumerate(stocks):
        zs = {fac: z[fac][i] for fac in FACTORS}
        present = [(fac, zs[fac]) for fac in FACTORS if zs[fac] is not None]
        comp = (sum(weights[f] * v for f, v in present) / sum(weights[f] for f, _ in present)) if present else None
        out.append({**s, 'z': zs, 'composite': comp})
    out.sort(key=lambda s: (s['composite'] is not None, s['composite'] if s['composite'] is not None else -1e9),
             reverse=True)
    return out


# ---------------------------------------------------------------------------
# Trend / market regime
# ---------------------------------------------------------------------------
def sma(closes, window):
    w = [c for c in (closes or [])[-window:] if c]
    return (sum(w) / len(w)) if len(w) >= max(2, window // 2) else None


def trend_signal(closes, window=200):
    """Price vs its SMA. Returns {price, sma, above, pct_vs_sma, signal: 'up'|'down'|None}.
    The 200-day MA is the daily analogue of Faber's 10-month-SMA timing rule."""
    if not closes:
        return {'price': None, 'sma': None, 'above': None, 'pct_vs_sma': None, 'signal': None}
    px = closes[-1]
    s = sma(closes, window)
    if s is None or not px:
        return {'price': px, 'sma': s, 'above': None, 'pct_vs_sma': None, 'signal': None}
    return {'price': px, 'sma': s, 'above': px > s,
            'pct_vs_sma': (px / s - 1.0) * 100.0, 'signal': 'up' if px > s else 'down'}


def regime_gauge(signals):
    """signals: list of trend_signal dicts (or 'up'/'down' strings). Returns the breadth gauge
    {pct_up, n, risk_on} — risk-on when a majority of tracked names are above their 200-day MA."""
    flags = []
    for s in signals or []:
        sig = s.get('signal') if isinstance(s, dict) else s
        if sig in ('up', 'down'):
            flags.append(sig == 'up')
    if not flags:
        return {'pct_up': None, 'n': 0, 'risk_on': None}
    pct = 100.0 * sum(flags) / len(flags)
    return {'pct_up': pct, 'n': len(flags), 'risk_on': pct >= 50.0}
