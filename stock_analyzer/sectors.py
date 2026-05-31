"""
Sector oversold / rebound-setup analysis — pure math, NO network (so it's testable).
Operates on the 11 SPDR GICS sector ETFs as sector proxies. Feed a list of daily closes
(oldest -> newest) to oversold_metrics(); fetching happens in the caller (run_screen.py).
"""

# Broad GICS Level-1 sectors (the 11 SPDR sector ETFs).
SECTORS = {
    'XLK': 'Technology', 'XLC': 'Communication Services', 'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples', 'XLE': 'Energy', 'XLF': 'Financials', 'XLV': 'Health Care',
    'XLI': 'Industrials', 'XLB': 'Materials', 'XLRE': 'Real Estate', 'XLU': 'Utilities',
}

# Granular industry / thematic ETFs — finer than GICS L1 so themes like SaaS, semis or
# biotech surface on their own instead of being buried inside "Technology" or "Health Care".
INDUSTRIES = {
    'IGV': 'Software / SaaS', 'SKYY': 'Cloud Computing', 'CIBR': 'Cybersecurity',
    'SMH': 'Semiconductors', 'XBI': 'Biotech', 'KRE': 'Regional Banks',
    'FINX': 'Fintech', 'XOP': 'Oil & Gas E&P', 'TAN': 'Solar / Clean Energy',
    'XHB': 'Homebuilders', 'XRT': 'Retail', 'ITA': 'Aerospace & Defense',
}

# Everything we track for the oversold/rebound screen, plus a group tag for the UI.
ALL_SECTORS = {**SECTORS, **INDUSTRIES}
GROUP = {**{s: 'Sector' for s in SECTORS}, **{s: 'Industry' for s in INDUSTRIES}}


def rsi(closes, period=14):
    """Wilder's RSI over the given closes (list, oldest -> newest). None if too short."""
    closes = [float(c) for c in closes if c == c]
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def oversold_metrics(closes):
    """Return oversold/rebound metrics for one sector's close series, or None if too short."""
    closes = [float(c) for c in closes if c == c]
    if len(closes) < 60:
        return None
    last = closes[-1]
    r = rsi(closes, 14)
    ma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 100 else None
    high_252 = max(closes[-252:]) if len(closes) >= 252 else max(closes)

    def ret(n):
        return ((last / closes[-n]) - 1) * 100 if (len(closes) > n and closes[-n]) else None

    pct_off_high = (last / high_252 - 1) * 100 if high_252 else 0.0
    pct_vs_200 = (last / ma200 - 1) * 100 if ma200 else None
    ret_1w, ret_1m, ret_3m = ret(5), ret(21), ret(63)

    # Rebound-setup score — _score_components() is the single source of truth (shared with the
    # UI breakdown), so the displayed components always reconcile with this total.
    score = sum(pts for _, pts in _score_components(r, pct_off_high, pct_vs_200, ret_1w, ret_1m, ret_3m))

    oversold = (r is not None and r < 42) or pct_off_high < -12

    def rnd(x):
        return round(x, 1) if x is not None else None

    return {
        'rsi': rnd(r), 'pct_off_52w_high': rnd(pct_off_high), 'pct_vs_200dma': rnd(pct_vs_200),
        'ret_1w': rnd(ret_1w), 'ret_1m': rnd(ret_1m), 'ret_3m': rnd(ret_3m),
        'rebound_score': round(score, 1), 'oversold': bool(oversold),
    }


def _score_components(rsi_v, pct_off_high, pct_vs_200, ret_1w, ret_1m, ret_3m):
    """The additive pieces of the rebound Setup score. Single source of truth, shared by
    oversold_metrics() (the total) and rebound_score_breakdown() (the per-piece UI table).
    Returns a list of (label, points)."""
    rsi_pts = max(0.0, 45 - rsi_v) * 1.1 if rsi_v is not None else 0.0
    dd_pts = max(0.0, -pct_off_high) * 0.6 if pct_off_high is not None else 0.0
    b200_pts = min(15.0, -pct_vs_200 * 0.5) if (pct_vs_200 is not None and pct_vs_200 < 0) else 0.0
    # The two stabilisation bonuses only fire once a group is actually pulled back (the three
    # technical pieces sum to >= 8), so a healthy uptrend can't rack up a high score.
    pulled_back = (rsi_pts + dd_pts + b200_pts) >= 8.0
    wk = 12.0 if (pulled_back and ret_1w is not None and ret_1w > 0) else 0.0
    dec = 10.0 if (pulled_back and ret_1m is not None and ret_3m is not None and ret_1m > ret_3m / 3) else 0.0
    return [('RSI depth', rsi_pts), ('Drawdown', dd_pts), ('Below 200-day', b200_pts),
            ('Week-up bonus', wk), ('Decelerating bonus', dec)]


def rebound_score_breakdown(m):
    """Per-component contributions to one group's Setup score, recomputed from its stored
    metrics so every number in the table is traceable. Returns (rows, total) where each row is
    {component, points, detail}."""
    rsi_v, off, vs200 = m.get('rsi'), m.get('pct_off_52w_high'), m.get('pct_vs_200dma')
    comps = _score_components(rsi_v, off, vs200, m.get('ret_1w'), m.get('ret_1m'), m.get('ret_3m'))
    details = {
        'RSI depth': (f"max(0, 45 − {rsi_v:.0f}) × 1.1" if rsi_v is not None else "—"),
        'Drawdown': (f"{-off:.0f}% off high × 0.6" if off is not None else "—"),
        'Below 200-day': (f"{-vs200:.0f}% below × 0.5 (cap 15)" if (vs200 is not None and vs200 < 0) else "at/above 200-day"),
        'Week-up bonus': "+12 · pulled back & last week up",
        'Decelerating bonus': "+10 · pulled back & 1m fall < ⅓ of 3m",
    }
    rows = [{'component': lbl, 'points': round(pts, 1), 'detail': details.get(lbl, '')} for lbl, pts in comps]
    return rows, round(sum(pts for _, pts in comps), 1)


def rank_oversold(sector_data, top=6, min_score=2.0):
    """sector_data: {sym: {name, ...metrics}}. Return the most beaten-down sectors (best
    rebound setup first). The per-sector 'oversold' flag marks the genuinely oversold ones;
    softer laggards are still surfaced (above min_score) so the list isn't empty in a strong
    market. Sectors in clear uptrends score ~0 and are excluded."""
    cands = [{'symbol': s, **m} for s, m in sector_data.items()
             if m and m.get('rebound_score', 0) >= min_score]
    cands.sort(key=lambda x: x.get('rebound_score', 0), reverse=True)
    return cands[:top]


def rule_note(m):
    """A short, deterministic plain-English read of one sector's setup."""
    bits = []
    if m.get('rsi') is not None:
        bits.append(f"RSI {m['rsi']:.0f} ({'oversold' if m['rsi'] < 35 else 'soft' if m['rsi'] < 45 else 'neutral'})")
    if m.get('pct_off_52w_high') is not None:
        bits.append(f"{m['pct_off_52w_high']:.0f}% off 52-wk high")
    if m.get('pct_vs_200dma') is not None:
        bits.append(f"{'below' if m['pct_vs_200dma'] < 0 else 'above'} 200-day avg")
    if m.get('ret_1w') is not None:
        bits.append("stabilising" if m['ret_1w'] > 0 else "still falling")
    return " · ".join(bits)


def status_label(m):
    """Where a group sits in the drawdown -> rebound cycle, for the Status column.

    The raw 'oversold' flag fires on EITHER a low RSI OR a deep drawdown, so a group that fell
    hard months ago but has since bounced (deep drawdown + recovered RSI) would read 'Oversold'
    even with RSI in the 60s — confusing. This separates the two: a name is only 'Oversold' while
    momentum is still weak; once RSI has recovered off a washed-out base it's 'Rebounding'.
    """
    rsi = m.get('rsi')
    off = m.get('pct_off_52w_high')
    deep = off is not None and off < -12          # still well below the 1-year high
    if rsi is None:
        return 'Oversold' if deep else 'Watch'
    if deep and rsi >= 50:
        return 'Rebounding'    # beaten down, but momentum has clearly turned up
    if rsi < 42 or deep:
        return 'Oversold'      # weak momentum now, or deep drawdown not yet turning
    return 'Watch'             # softening but not extreme
