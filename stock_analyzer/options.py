"""
Options analytics — Black-Scholes Greeks, volatility metrics, liquidity/yield, and a
rule engine for two conservative sleeves:
  • INCOME  — cash-secured puts, covered calls, the "wheel" (sell the volatility risk premium)
  • GROWTH  — long deep-ITM LEAPS calls (defined-risk leverage)

The maths core is PURE (no network, no Streamlit) so it is unit-testable offline; the only
network touch is fetch_option_chain(), which reuses the engine's curl_cffi Yahoo session.

EVIDENCE & HONESTY (see docs/options_strategy.md for citations):
  - The volatility risk premium (implied vol > subsequently realised vol ~78-85% of days) is the
    real, peer-reviewed edge behind premium selling. BUT the edge is RISK REDUCTION, not higher
    raw return (CBOE PUT index ~matched the S&P at ~2/3 the volatility, -32.7% vs -50.9% max DD),
    and it CAPS upside and is NOT a hedge (it loses in sharp moves either way).
  - The tactical defaults below (≈0.30-delta, 30-45 DTE, take profit at 50%, roll at 21 DTE) are
    widely-used PRACTITIONER CONVENTIONS (tastytrade-style), NOT independently-proven parameters.
    They are exposed as adjustable inputs in the UI. The durable edge is VRP + discipline +
    liquidity/earnings gating — not any single number.
  - LEAPS: theta is minimal early and bites in the final ~90 days, so prefer deep-ITM (~0.70-0.80
    delta), 12+ months out, roll before the last 90 days, and size for TOTAL loss of the premium.

Nothing here is financial advice — it mechanically applies rules the user sets and surfaces signals.
"""
import math
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Tunable defaults — every one of these is overridable from the UI.
# ---------------------------------------------------------------------------
DEFAULT_PARAMS = {
    # cash-secured put (income)
    'csp_delta': 0.30,          # target short-put delta (abs); 0.16 = more conservative
    'csp_dte_min': 30, 'csp_dte_max': 45,
    # covered call (income / wheel leg 2)
    'cc_delta': 0.30,           # target short-call delta; favour OTM over ATM
    'cc_dte_min': 30, 'cc_dte_max': 45,
    # LEAPS (growth)
    'leaps_delta': 0.75,        # target long-call delta (deep ITM)
    'leaps_dte_min': 365,       # 12+ months
    # gates
    'iv_rank_min': 30,          # sell premium only when IV-Rank >= this (when history exists)
    'iv_rv_min': 1.10,          # ...or when ATM IV / realised vol >= this (immediate VRP proxy)
    'min_open_interest': 100,   # liquidity
    'min_volume': 0,
    'max_spread_pct': 10.0,     # bid-ask spread as % of mid
    # management / sizing (informational)
    'profit_take_pct': 50, 'roll_dte': 21, 'leaps_roll_dte': 90,
    'max_pos_pct': 5.0,         # suggested cap per position, % of portfolio
    # pricing
    'risk_free': 0.043, 'div_yield': 0.0,
}

CONTRACT_MULTIPLIER = 100


# ---------------------------------------------------------------------------
# Black-Scholes (no SciPy dependency)
# ---------------------------------------------------------------------------
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _years(dte):
    return max(float(dte), 0.0) / 365.0


def bs_d1(S, K, T, r, sigma, q=0.0):
    if not (S and S > 0) or not (K and K > 0) or T <= 0 or not (sigma and sigma > 0):
        return None
    return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def bs_delta(S, K, T, r, sigma, kind='call', q=0.0):
    """Black-Scholes delta. Calls in [0,1]; puts in [-1,0]. None if inputs are degenerate."""
    d1 = bs_d1(S, K, T, r, sigma, q)
    if d1 is None:
        return None
    disc = math.exp(-q * T)
    return disc * _norm_cdf(d1) if kind == 'call' else disc * (_norm_cdf(d1) - 1.0)


def bs_price(S, K, T, r, sigma, kind='call', q=0.0):
    d1 = bs_d1(S, K, T, r, sigma, q)
    if d1 is None:
        return None
    d2 = d1 - sigma * math.sqrt(T)
    if kind == 'call':
        return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def bs_theta_per_day(S, K, T, r, sigma, kind='call', q=0.0):
    """Theta per CALENDAR day (negative for long options)."""
    d1 = bs_d1(S, K, T, r, sigma, q)
    if d1 is None:
        return None
    d2 = d1 - sigma * math.sqrt(T)
    term1 = -(S * math.exp(-q * T) * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    if kind == 'call':
        theta = (term1 - r * K * math.exp(-r * T) * _norm_cdf(d2)
                 + q * S * math.exp(-q * T) * _norm_cdf(d1))
    else:
        theta = (term1 + r * K * math.exp(-r * T) * _norm_cdf(-d2)
                 - q * S * math.exp(-q * T) * _norm_cdf(-d1))
    return theta / 365.0


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------
def realized_vol(closes, window=30):
    """Annualised realised volatility from a close-price series (last `window` daily returns)."""
    if not closes or len(closes) < 6:
        return None
    rets = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a and b and a > 0 and b > 0:
            rets.append(math.log(b / a))
    rets = rets[-window:]
    if len(rets) < 5:
        return None
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var * 252.0)


def iv_rank(current_iv, iv_history):
    """IV-Rank as a 0-100 percentile of current IV within a history list (None if too short)."""
    hist = [h for h in (iv_history or []) if h is not None]
    if current_iv is None or len(hist) < 20:
        return None
    below = sum(1 for h in hist if h <= current_iv)
    return round(100.0 * below / len(hist), 1)


def premium_is_rich(atm_iv, rv, ivr, params):
    """True when it's a reasonable time to SELL premium: IV-Rank gate (if available) OR IV/RV gate."""
    if ivr is not None:
        return ivr >= params.get('iv_rank_min', 30)
    if atm_iv and rv and rv > 0:
        return (atm_iv / rv) >= params.get('iv_rv_min', 1.10)
    return False


# ---------------------------------------------------------------------------
# Contract helpers (operate on plain dicts: strike, bid, ask, last, volume, oi, iv)
# ---------------------------------------------------------------------------
def _f(x, default=0.0):
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def mid_price(c):
    bid, ask = _f(c.get('bid')), _f(c.get('ask'))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return _f(c.get('last')) or (ask if ask > 0 else bid)


def spread_pct(c):
    bid, ask = _f(c.get('bid')), _f(c.get('ask'))
    m = mid_price(c)
    if m <= 0 or bid <= 0 or ask <= 0:
        return None
    return (ask - bid) / m * 100.0


def is_liquid(c, params):
    sp = spread_pct(c)
    return (_f(c.get('oi')) >= params.get('min_open_interest', 100)
            and _f(c.get('volume')) >= params.get('min_volume', 0)
            and _f(c.get('bid')) > 0
            and sp is not None and sp <= params.get('max_spread_pct', 10.0))


def enrich(c, S, dte, kind, params):
    """Add mid / spread / delta / liquidity to a contract dict (non-mutating copy)."""
    r, q = params.get('risk_free', 0.043), params.get('div_yield', 0.0)
    T = _years(dte)
    sigma = _f(c.get('iv'))
    out = dict(c)
    out['mid'] = mid_price(c)
    out['spread_pct'] = spread_pct(c)
    out['dte'] = dte
    out['delta'] = bs_delta(S, _f(c.get('strike')), T, r, sigma, kind, q)
    out['liquid'] = is_liquid(c, params)
    return out


def _closest_by_delta(contracts, target_abs_delta):
    cands = [c for c in contracts if c.get('delta') is not None]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(abs(c['delta']) - target_abs_delta))


# ---------------------------------------------------------------------------
# Candidate finders — each returns a dict (or None) describing the best contract.
# ---------------------------------------------------------------------------
def find_csp(puts, S, dte, params):
    """Best cash-secured put: liquid OTM put nearest the target delta."""
    pool = [enrich(c, S, dte, 'put', params) for c in puts]
    pool = [c for c in pool if c['liquid'] and _f(c.get('strike')) < S and c['delta'] is not None]
    best = _closest_by_delta(pool, params.get('csp_delta', 0.30))
    if not best:
        return None
    K, mid = _f(best['strike']), best['mid']
    cash = K * CONTRACT_MULTIPLIER
    breakeven = K - mid
    return {
        'kind': 'csp', 'strike': K, 'dte': dte, 'mid': mid,
        'delta': best['delta'], 'iv': _f(best.get('iv')), 'oi': int(_f(best.get('oi'))),
        'spread_pct': best['spread_pct'],
        'premium_total': mid * CONTRACT_MULTIPLIER,
        'cash_secured': cash,
        'ann_yield_pct': (mid / K) * (365.0 / dte) * 100.0 if K > 0 and dte > 0 else None,
        'breakeven': breakeven,
        'downside_buffer_pct': (S - breakeven) / S * 100.0 if S > 0 else None,
    }


def find_covered_call(calls, S, dte, params, cost_basis=None):
    """Best covered call: liquid OTM call nearest the target delta (favours OTM over ATM).
    If cost_basis is given, only strikes at/above it (don't lock in a loss)."""
    floor = max(S, cost_basis) if cost_basis else S
    pool = [enrich(c, S, dte, 'call', params) for c in calls]
    pool = [c for c in pool if c['liquid'] and _f(c.get('strike')) >= floor and c['delta'] is not None]
    best = _closest_by_delta(pool, params.get('cc_delta', 0.30))
    if not best:
        return None
    K, mid = _f(best['strike']), best['mid']
    return {
        'kind': 'covered_call', 'strike': K, 'dte': dte, 'mid': mid,
        'delta': best['delta'], 'iv': _f(best.get('iv')), 'oi': int(_f(best.get('oi'))),
        'spread_pct': best['spread_pct'],
        'premium_total': mid * CONTRACT_MULTIPLIER,
        'ann_yield_pct': (mid / S) * (365.0 / dte) * 100.0 if S > 0 and dte > 0 else None,
        'otm_pct': (K - S) / S * 100.0 if S > 0 else None,
        'max_gain_if_called_pct': ((K - S) + mid) / S * 100.0 if S > 0 else None,
    }


def find_leaps(calls, S, dte, params):
    """Best LEAPS call: liquid deep-ITM call nearest the target delta (~0.75)."""
    pool = [enrich(c, S, dte, 'call', params) for c in calls]
    pool = [c for c in pool if c['liquid'] and _f(c.get('strike')) < S and c['delta'] is not None]
    best = _closest_by_delta(pool, params.get('leaps_delta', 0.75))
    if not best:
        return None
    K, mid = _f(best['strike']), best['mid']
    intrinsic = max(S - K, 0.0)
    extrinsic = max(mid - intrinsic, 0.0)
    return {
        'kind': 'leaps', 'strike': K, 'dte': dte, 'mid': mid,
        'delta': best['delta'], 'iv': _f(best.get('iv')), 'oi': int(_f(best.get('oi'))),
        'spread_pct': best['spread_pct'],
        'debit_total': mid * CONTRACT_MULTIPLIER,
        'breakeven': K + mid,
        'breakeven_move_pct': ((K + mid) - S) / S * 100.0 if S > 0 else None,
        'extrinsic': extrinsic,
        'extrinsic_pct': (extrinsic / mid * 100.0) if mid > 0 else None,
        'capital_efficiency': (best['delta'] * S) / mid if mid > 0 and best['delta'] else None,
    }


# ---------------------------------------------------------------------------
# Expiry selection + ATM IV
# ---------------------------------------------------------------------------
def days_to(expiry, today=None):
    """Whole days from today to an 'YYYY-MM-DD' expiry string."""
    today = today or date.today()
    try:
        e = datetime.strptime(expiry, '%Y-%m-%d').date()
        return (e - today).days
    except (ValueError, TypeError):
        return None


def _pick_expiry(dtes, lo, hi):
    """Choose the expiry whose DTE sits in [lo,hi] closest to the window mid; else nearest to lo."""
    in_win = [d for d in dtes if lo <= d <= hi]
    if in_win:
        mid = (lo + hi) / 2.0
        return min(in_win, key=lambda d: abs(d - mid))
    future = [d for d in dtes if d >= max(7, lo - 10)]
    return min(future, key=lambda d: abs(d - lo)) if future else None


def total_oi(chain):
    """Total open interest across a {'calls':[...],'puts':[...]} expiry (a liquidity proxy)."""
    return (sum(_f(c.get('oi')) for c in chain.get('calls', []))
            + sum(_f(c.get('oi')) for c in chain.get('puts', [])))


def _pick_income_expiry(chains, exp_dte, lo, hi):
    """Income expiry = the MOST LIQUID expiry in a tolerant DTE window [lo-10, hi+15]. This favours the
    standard monthly (3rd-Friday) over thin weeklies that merely land inside the exact window."""
    win = [e for e in chains if e in exp_dte and max(7, lo - 10) <= exp_dte[e] <= hi + 15]
    if win:
        return max(win, key=lambda e: total_oi(chains[e]))
    fut = [e for e in chains if e in exp_dte and exp_dte[e] >= max(7, lo - 10)]
    return min(fut, key=lambda e: exp_dte[e]) if fut else None


def atm_iv(contracts, S):
    """Implied vol of the strike nearest spot (the near-the-money IV)."""
    cands = [c for c in contracts if _f(c.get('iv')) > 0 and _f(c.get('strike')) > 0]
    if not cands:
        return None
    near = min(cands, key=lambda c: abs(_f(c['strike']) - S))
    return _f(near.get('iv'))


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------
def evaluate(chains, spot, closes=None, iv_history=None, params=None,
             earnings_in_days=None, cost_basis=None, today=None):
    """Evaluate one underlying.

    chains: {expiry_str: {'calls': [contract dicts], 'puts': [contract dicts]}}
    spot:   underlying price.  closes: recent daily closes (for realised vol).
    iv_history: list of past ATM-IV readings (for IV-Rank; optional).
    Returns a structured dict: {spot, vol:{...}, gates:{...}, csp, covered_call, leaps, notes:[...]}.
    """
    params = {**DEFAULT_PARAMS, **(params or {})}
    notes = []
    # DTE per expiry
    exp_dte = {e: days_to(e, today) for e in chains}
    exp_dte = {e: d for e, d in exp_dte.items() if d is not None and d >= 0}
    dtes = sorted(exp_dte.values())

    out = {'spot': spot,
           'vol': {'atm_iv': None, 'realized_vol': None, 'iv_rv': None, 'iv_rank': None},
           'gates': {'premium_rich': False, 'earnings_soon': False, 'earnings_in_days': earnings_in_days},
           'csp': None, 'covered_call': None, 'leaps': None, 'notes': notes, 'params': params}
    if not chains or not dtes:
        notes.append('No option chains available.')
        return out

    # Income expiry = the most-liquid expiry near the 30-45 DTE window (favours the standard monthly).
    # Read the ATM IV from it — a clean ~monthly volatility gauge.
    inc_e = _pick_income_expiry(chains, exp_dte, params['csp_dte_min'], params['csp_dte_max'])
    inc_dte = exp_dte.get(inc_e)
    iv_exp = inc_e or min(chains, key=lambda e: abs(exp_dte.get(e, 9999) - 30))
    a_iv = atm_iv(chains.get(iv_exp, {}).get('calls', []) + chains.get(iv_exp, {}).get('puts', []), spot)
    rv = realized_vol(closes, 30) if closes else None
    ivr = iv_rank(a_iv, iv_history)
    rich = premium_is_rich(a_iv, rv, ivr, params)
    out['vol'] = {'atm_iv': a_iv, 'realized_vol': rv,
                  'iv_rv': (a_iv / rv) if (a_iv and rv and rv > 0) else None, 'iv_rank': ivr}
    earnings_soon = (earnings_in_days is not None and 0 <= earnings_in_days <= params['csp_dte_max'])
    out['gates'] = {'premium_rich': rich, 'earnings_soon': earnings_soon, 'earnings_in_days': earnings_in_days}

    # ---- income sleeve: only when premium is rich and not across earnings ----
    if not rich:
        notes.append('Premium not rich enough to sell (IV-Rank / IV-vs-realised below the gate) — '
                     'income sleeve on hold.')
    elif earnings_soon:
        notes.append(f'Earnings in ~{earnings_in_days}d (before the income expiry) — '
                     'skip selling premium across the event.')
    elif inc_e:
        out['csp'] = find_csp(chains[inc_e].get('puts', []), spot, inc_dte, params)
        out['covered_call'] = find_covered_call(chains[inc_e].get('calls', []), spot, inc_dte,
                                                params, cost_basis=cost_basis)
        if out['csp'] is None and out['covered_call'] is None:
            notes.append('No liquid contract near the target delta in the income window.')
    else:
        notes.append('No suitable income-sleeve expiry (~30-45 DTE) in the fetched chains.')

    # ---- growth sleeve: longest expiry >= leaps_dte_min, prefer LOWER IV at entry ----
    leaps_dtes = [d for d in dtes if d >= params['leaps_dte_min']]
    if leaps_dtes:
        ldte = max(leaps_dtes)
        le = next((e for e, d in exp_dte.items() if d == ldte), None)
        if le:
            out['leaps'] = find_leaps(chains[le].get('calls', []), spot, ldte, params)
            if out['leaps'] is None:
                notes.append('No liquid deep-ITM LEAPS call near the target delta.')
        if rich:
            notes.append('Note: IV looks elevated — less ideal for BUYING LEAPS (you pay up for vol).')
    else:
        notes.append('No expiry 12+ months out — no LEAPS available for the growth sleeve.')

    return out


# ---------------------------------------------------------------------------
# IV history (persisted nightly; powers IV-Rank). Pure dict transforms.
# ---------------------------------------------------------------------------
def iv_history_values(history, ticker):
    """Past ATM-IV readings for a ticker as a plain float list (for iv_rank)."""
    return [e.get('iv') for e in (history or {}).get(ticker, []) if e.get('iv') is not None]


def update_iv_history(history, ticker, date_str, atm_iv, cap=252):
    """Append today's ATM IV to the rolling per-ticker history (one entry per date, capped).
    Pure — returns a NEW dict; the caller persists it. No-op when atm_iv is None."""
    history = dict(history or {})
    if atm_iv is None:
        return history
    series = [e for e in history.get(ticker, []) if e.get('date') != date_str]
    series.append({'date': date_str, 'iv': round(float(atm_iv), 4)})
    history[ticker] = series[-cap:]
    return history


# ---------------------------------------------------------------------------
# Open-position management — pure alert rules (live quote injected by the caller)
# ---------------------------------------------------------------------------
def option_kind(strategy):
    """Option type for a tracked strategy: cash-secured put -> put, else call."""
    return 'put' if strategy == 'csp' else 'call'


def is_short(strategy):
    """True for premium-selling (short) positions; LEAPS are long."""
    return strategy in ('csp', 'covered_call')


def find_contract(contracts, strike):
    """The contract whose strike is nearest `strike` (None if the chain is empty)."""
    cands = [c for c in (contracts or []) if c.get('strike') is not None]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(_f(c['strike']) - strike))


def position_pl(pos, mid):
    """Per-position P/L in dollars and % of the opening premium. Short profits as the option
    decays (mid < open); long profits as it appreciates (mid > open). None if not computable."""
    op = pos.get('open_price') or 0
    n = (pos.get('contracts') or 1) * CONTRACT_MULTIPLIER
    if mid is None or not op:
        return {'pl_dollars': None, 'pl_pct': None}
    if is_short(pos.get('strategy')):
        return {'pl_dollars': (op - mid) * n, 'pl_pct': (op - mid) / op * 100}
    return {'pl_dollars': (mid - op) * n, 'pl_pct': (mid - op) / op * 100}


def position_alerts(pos, live, params=None):
    """Action flags for one open position given a live snapshot.
    live = {mid, delta, spot, dte, earnings_in_days}. Returns [{level, label, detail}] where
    level is 'red' | 'amber' | 'green'. Pure — the caller supplies the live data."""
    params = {**DEFAULT_PARAMS, **(params or {})}
    strat = pos.get('strategy')
    K = float(pos.get('strike') or 0)
    op = pos.get('open_price') or 0
    kind = option_kind(strat)
    mid, delta = live.get('mid'), live.get('delta')
    spot, dte, eid = live.get('spot'), live.get('dte'), live.get('earnings_in_days')
    A = []
    if is_short(strat):
        if op and mid is not None:
            captured = (op - mid) / op * 100
            if captured >= params['profit_take_pct']:
                A.append({'level': 'green', 'label': f"Take profit — {captured:.0f}% of max captured",
                          'detail': f"buy back near ${mid:.2f} (sold ${op:.2f})"})
        tested = ((delta is not None and abs(delta) >= 0.45)
                  or (kind == 'put' and spot is not None and spot <= K)
                  or (kind == 'call' and spot is not None and spot >= K))
        if tested:
            d = f", Δ {abs(delta):.2f}" if delta is not None else ""
            sp = f"${spot:.2f}" if spot is not None else "?"
            A.append({'level': 'red', 'label': "Strike tested — assignment risk",
                      'detail': f"spot {sp} vs strike ${K:.0f}{d}"})
        if dte is not None and dte <= params['roll_dte']:
            A.append({'level': 'amber', 'label': f"{dte} DTE — manage",
                      'detail': f"at/under your {params['roll_dte']}-DTE rule (roll out or close)"})
        if eid is not None and 0 <= eid <= (dte if dte is not None else 10**9):
            A.append({'level': 'amber', 'label': f"Earnings in ~{eid}d",
                      'detail': "event risk before expiry on a short premium position"})
    else:  # long LEAPS
        if dte is not None and dte <= params.get('leaps_roll_dte', 90):
            A.append({'level': 'amber', 'label': f"{dte} DTE — roll the LEAPS",
                      'detail': "theta accelerates inside ~90 DTE"})
        if op and mid is not None:
            pct = (mid - op) / op * 100
            if pct <= -50:
                A.append({'level': 'red', 'label': f"Down {abs(pct):.0f}% — thesis check",
                          'detail': "long premium eroding; re-underwrite or cut"})
            elif pct >= 50:
                A.append({'level': 'green', 'label': f"Up {pct:.0f}%",
                          'detail': "consider trimming or rolling up to lock gains"})
    if not A:
        A.append({'level': 'green', 'label': "On track", 'detail': "no action triggered"})
    return A


# ---------------------------------------------------------------------------
# Network: fetch + normalise an option chain (the only impure function)
# ---------------------------------------------------------------------------
def normalize_chain(df):
    """yfinance calls/puts DataFrame -> list of plain dicts the pure functions consume."""
    if df is None:
        return []
    try:
        recs = df.to_dict('records')
    except AttributeError:
        recs = list(df)
    out = []
    for r in recs:
        out.append({
            'strike': r.get('strike'), 'bid': r.get('bid'), 'ask': r.get('ask'),
            'last': r.get('lastPrice'), 'volume': r.get('volume'),
            'oi': r.get('openInterest'), 'iv': r.get('impliedVolatility'),
        })
    return out


def fetch_option_chain(ticker, near_expiries=14, far_expiries=3, ticker_obj=None):
    """Fetch option chains for `ticker`, reusing the engine's curl_cffi session by default.
    Pulls the NEAREST expiries (for the 30-45 DTE income sleeve) AND the FARTHEST ones (for
    12-month+ LEAPS, which sit at the end of Yahoo's ascending expiry list). Returns (chains, meta):
      chains = {expiry: {'calls': [..], 'puts': [..]}}
      meta   = {'spot': float|None, 'earnings_in_days': int|None}
    Best-effort: returns ({}, {...}) on failure rather than raising."""
    from .alpha_engine import _yf_ticker, safe_get
    t = ticker_obj or _yf_ticker(ticker)
    chains, meta = {}, {'spot': None, 'earnings_in_days': None}

    expiries = safe_get(lambda: list(t.options or []), []) or []
    # nearest (income) + farthest (LEAPS), de-duplicated, order preserved
    chosen, seen = [], set()
    for exp in list(expiries[:near_expiries]) + list(expiries[-far_expiries:] if far_expiries else []):
        if exp not in seen:
            seen.add(exp)
            chosen.append(exp)
    for exp in chosen:
        oc = safe_get(lambda: t.option_chain(exp))
        if oc is None:
            continue
        calls = normalize_chain(safe_get(lambda: oc.calls))
        puts = normalize_chain(safe_get(lambda: oc.puts))
        if calls or puts:
            chains[exp] = {'calls': calls, 'puts': puts}

    # spot
    fi = safe_get(lambda: t.fast_info) or {}
    meta['spot'] = safe_get(lambda: fi.get('last_price')) or safe_get(lambda: fi.get('lastPrice'))
    if not meta['spot']:
        hist = safe_get(lambda: t.history(period='1d'))
        if hist is not None and not hist.empty:
            meta['spot'] = float(hist['Close'].iloc[-1])

    # next earnings date -> days from now (best-effort; often unavailable)
    def _earn_days():
        cal = safe_get(lambda: t.calendar)
        ed = None
        if isinstance(cal, dict):
            v = cal.get('Earnings Date')
            ed = v[0] if isinstance(v, (list, tuple)) and v else v
        if ed is None:
            return None
        d = ed.date() if hasattr(ed, 'date') else ed
        return (d - date.today()).days
    meta['earnings_in_days'] = safe_get(_earn_days)
    return chains, meta


def quote_position(ticker, expiry, strike, kind, params=None, today=None, ticker_obj=None):
    """Live snapshot for one tracked contract (a specific expiry+strike): fetch that expiry's chain,
    find the nearest strike, and compute the current mid + Black-Scholes delta. Returns a dict
    {mid, delta, iv, spot, dte, earnings_in_days, strike_found} or None. Network; best-effort."""
    from .alpha_engine import _yf_ticker, safe_get
    params = {**DEFAULT_PARAMS, **(params or {})}
    t = ticker_obj or _yf_ticker(ticker)
    oc = safe_get(lambda: t.option_chain(expiry))
    if oc is None:
        return None
    contracts = normalize_chain(safe_get(lambda: (oc.puts if kind == 'put' else oc.calls)))
    c = find_contract(contracts, strike)
    fi = safe_get(lambda: t.fast_info) or {}
    spot = safe_get(lambda: fi.get('last_price')) or safe_get(lambda: fi.get('lastPrice'))
    if not spot:
        h = safe_get(lambda: t.history(period='1d'))
        if h is not None and not h.empty:
            spot = float(h['Close'].iloc[-1])
    dte = days_to(expiry, today)
    out = {'mid': None, 'delta': None, 'iv': None, 'spot': spot, 'dte': dte,
           'earnings_in_days': None, 'strike_found': None}
    if c:
        out['mid'] = mid_price(c)
        out['iv'] = _f(c.get('iv'))
        out['strike_found'] = _f(c.get('strike'))
        if spot and dte and dte > 0:
            out['delta'] = bs_delta(spot, _f(c.get('strike')), _years(dte),
                                    params['risk_free'], _f(c.get('iv')), kind, params['div_yield'])

    def _earn_days():
        cal = safe_get(lambda: t.calendar)
        ed = None
        if isinstance(cal, dict):
            v = cal.get('Earnings Date')
            ed = v[0] if isinstance(v, (list, tuple)) and v else v
        if ed is None:
            return None
        d = ed.date() if hasattr(ed, 'date') else ed
        return (d - (today or date.today())).days
    out['earnings_in_days'] = safe_get(_earn_days)
    return out
