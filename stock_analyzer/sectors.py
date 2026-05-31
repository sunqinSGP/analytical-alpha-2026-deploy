"""
Sector oversold / rebound-setup analysis — pure math, NO network (so it's testable).
Operates on the 11 SPDR GICS sector ETFs as sector proxies. Feed a list of daily closes
(oldest -> newest) to oversold_metrics(); fetching happens in the caller (run_screen.py).
"""

SECTORS = {
    'XLK': 'Technology', 'XLC': 'Communication Services', 'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples', 'XLE': 'Energy', 'XLF': 'Financials', 'XLV': 'Health Care',
    'XLI': 'Industrials', 'XLB': 'Materials', 'XLRE': 'Real Estate', 'XLU': 'Utilities',
}


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

    # Rebound-setup score: reward being oversold (low RSI, deep drawdown, below 200dma)
    # AND showing signs of stabilising (recent week up; 1-month decline shallower than 3-month).
    base = 0.0
    if r is not None:
        base += max(0.0, 45 - r) * 1.1
    base += max(0.0, -pct_off_high) * 0.6
    if pct_vs_200 is not None and pct_vs_200 < 0:
        base += min(15.0, -pct_vs_200 * 0.5)
    score = base
    # Stabilisation bonus only for sectors that are ACTUALLY pulled back — otherwise a
    # rising sector (recent week up, decline shallow) would score like a rebound setup.
    if base >= 8.0:
        if ret_1w is not None and ret_1w > 0:
            score += 12.0
        if ret_1m is not None and ret_3m is not None and ret_1m > ret_3m / 3:
            score += 10.0

    oversold = (r is not None and r < 42) or pct_off_high < -12

    def rnd(x):
        return round(x, 1) if x is not None else None

    return {
        'rsi': rnd(r), 'pct_off_52w_high': rnd(pct_off_high), 'pct_vs_200dma': rnd(pct_vs_200),
        'ret_1w': rnd(ret_1w), 'ret_1m': rnd(ret_1m), 'ret_3m': rnd(ret_3m),
        'rebound_score': round(score, 1), 'oversold': bool(oversold),
    }


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
