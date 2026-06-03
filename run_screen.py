"""
Nightly screener for Analytical Alpha — runs unattended (e.g. Windows Task Scheduler).
Scans the curated universe, assigns conviction tiers, and writes data/screen_results.json,
which the app then loads instantly (no waiting, no live scan needed). No Streamlit required.

    python run_screen.py
"""
import os
import sys
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stock_analyzer.alpha_engine import alpha_analysis, assign_screen_tier, _yf_ticker
from stock_analyzer.universe import WATCHLIST, SMALLCAP_UNIVERSE
from stock_analyzer import sectors as sct
from stock_analyzer import options as opt
from stock_analyzer import positions as posn
from stock_analyzer import strategy as strat

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'screen_results.json')
IVH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'iv_history.json')
POS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'options_positions.json')
SC_BLOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'smallcap_block.json')
# US-listed names (plain symbols, no exchange suffix) are the reliably option-able set.
US_OPTIONABLE = [tk for tk in WATCHLIST if '.' not in tk]


def screen_one(tk):
    try:
        r = alpha_analysis(tk)
        if 'error' in r:
            return None
        moat = r['qualitative']['moat']
        rf = r['risk_management']['risk_factors']
        nrr = r['quantitative']['net_revenue_retention'].get('estimated_nrr_pct')
        infl = r['quantitative']['forward_rule_of_40'].get('inflection_signal', '') or ''
        tier = assign_screen_tier(moat['moat_rating'], rf['risk_score'],
                                  r['qualitative']['moat_performance']['performance'],
                                  nrr, infl, moat.get('circumvention_delta', 0))
        info = r['data'].get('info') or {}
        pdat = r['data'].get('price_data')
        closes = ([float(x) for x in pdat['Close'].dropna().tolist()]
                  if pdat is not None and getattr(pdat, 'empty', True) is False and 'Close' in pdat else [])
        return {
            'ticker': tk, 'name': r['data']['name'], 'nob': r['nob']['name'],
            'moat': round(moat['moat_rating'], 1), 'circ_delta': moat.get('circumvention_delta', 0),
            'moat_trend': r['qualitative']['moat_performance']['performance'],
            'risk': rf['risk_score'], 'risk_level': rf['risk_level'],
            'nrr': round(nrr) if nrr is not None else None, 'fwd_inflection': infl,
            'conviction': r['thesis']['conviction'], 'price': r['data']['price'],
            'sector': r['data']['sector'], 'tier': tier,
            'factors': strat.stock_factor_raw(info, closes),
            'trend': strat.trend_signal(closes),
        }
    except Exception:
        return None


def screen_sectors():
    """Oversold/rebound metrics for the broad GICS sectors + granular industry/theme ETFs
    (price-based, no LLM). Each entry carries a 'group' tag (Sector vs Industry)."""
    out = {}
    for sym, name in sct.ALL_SECTORS.items():
        try:
            hist = _yf_ticker(sym).history(period='2y')
            if hist is not None and not hist.empty and 'Close' in hist.columns:
                m = sct.oversold_metrics(hist['Close'].tolist())
                if m:
                    out[sym] = {'name': name, 'group': sct.GROUP.get(sym, 'Sector'), **m}
        except Exception:
            pass
    return out


def _scan(tickers, workers):
    rows, skipped = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(screen_one, tk): tk for tk in tickers}
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                rows.append(row)
            else:
                skipped.append(futs[fut])
    return rows, skipped


def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def screen_option_one(tk, iv_hist):
    """Fetch + evaluate one ticker's options into a compact row for the saved scan (or None)."""
    try:
        chains, meta = opt.fetch_option_chain(tk, near_expiries=10, far_expiries=1)
        if not chains:
            return None
        spot = meta.get('spot')
        hist = _yf_ticker(tk).history(period='3mo')
        closes = [float(x) for x in hist['Close'].dropna().tolist()] if hist is not None and not hist.empty else []
        oe = opt.evaluate(chains, spot, closes=closes,
                          iv_history=opt.iv_history_values(iv_hist, tk),
                          earnings_in_days=meta.get('earnings_in_days'))
        v, g, csp, lp = oe['vol'], oe['gates'], oe['csp'], oe['leaps']
        return {
            'ticker': tk, 'spot': round(spot, 2) if spot else None,
            'atm_iv': v['atm_iv'], 'iv_rv': round(v['iv_rv'], 2) if v['iv_rv'] else None,
            'iv_rank': v['iv_rank'], 'premium_rich': g['premium_rich'],
            'earnings_in_days': g['earnings_in_days'],
            'csp': None if not csp else {
                'strike': csp['strike'], 'delta': round(csp['delta'], 2), 'dte': csp['dte'],
                'premium': round(csp['mid'], 2),
                'ann_yield_pct': round(csp['ann_yield_pct'], 1) if csp['ann_yield_pct'] else None,
                'oi': csp['oi']},
            'leaps': None if not lp else {'strike': lp['strike'], 'delta': round(lp['delta'], 2), 'dte': lp['dte']},
        }
    except Exception:
        return None


def screen_options(tickers, iv_hist, workers=4):
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(screen_option_one, tk, iv_hist): tk for tk in tickers}
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                rows.append(r)
    return rows


def screen_position_one(p):
    """Live-quote one tracked position and compute its management alerts (or None)."""
    try:
        q = opt.quote_position(p['ticker'], p['expiry'], p['strike'], opt.option_kind(p['strategy']))
        if not q:
            return None
        alerts = opt.position_alerts(p, q)
        pl = opt.position_pl(p, q.get('mid'))
        return {
            'ticker': p['ticker'], 'strategy': p['strategy'],
            'label': posn.STRATEGY_LABELS.get(p['strategy'], p['strategy']),
            'strike': p['strike'], 'expiry': p['expiry'], 'contracts': p['contracts'],
            'dte': q.get('dte'), 'mid': q.get('mid'),
            'pl_pct': round(pl['pl_pct']) if pl['pl_pct'] is not None else None,
            'alerts': alerts, 'actionable': sum(1 for a in alerts if a['level'] in ('red', 'amber')),
        }
    except Exception:
        return None


def screen_positions(positions, workers=3):
    rows = []
    if not positions:
        return rows
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(screen_position_one, p): p for p in positions}
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                rows.append(r)
    return rows


def screen_smallcap_one(tk):
    """Fetch one small-cap candidate, apply the quality/investability gate, and (if it clears)
    compute factor signals + trend. Returns a row tagged pass/drop, or None on a fetch error."""
    try:
        t = _yf_ticker(tk)
        info = t.info or {}
        hist = t.history(period='2y')
        closes = ([float(x) for x in hist['Close'].dropna().tolist()]
                  if hist is not None and not hist.empty and 'Close' in hist.columns else [])
        gate = strat.smallcap_gate(info, closes)
        row = {
            'ticker': tk, 'name': info.get('shortName') or info.get('longName') or tk,
            'sector': info.get('sector'), 'mcap': gate['mcap'], 'price': gate['price'],
            'pass': gate['pass'], 'reasons': gate['reasons'],
        }
        if gate['pass']:
            row['factors'] = strat.stock_factor_raw(info, closes)
            row['trend'] = strat.trend_signal(closes)
        return row
    except Exception:
        return None


def screen_smallcap(tickers, workers=5):
    """Scan the small-cap universe (with one gentle retry for fetch failures).
    Returns (survivor_rows, dropped_rows, failed_tickers)."""
    survivors, dropped, failed = [], [], []

    def _run(tks, w):
        with ThreadPoolExecutor(max_workers=w) as ex:
            futs = {ex.submit(screen_smallcap_one, tk): tk for tk in tks}
            for fut in as_completed(futs):
                r = fut.result()
                if not r:
                    failed.append(futs[fut])
                elif r.get('pass'):
                    survivors.append(r)
                else:
                    dropped.append(r)

    _run(tickers, workers)
    if failed:
        retry, failed = failed[:], []
        time.sleep(3)
        _run(retry, max(2, workers - 2))
    return survivors, dropped, failed


def _build_smallcap_block(survivors, dropped, failed):
    """Assemble the saved 'smallcap' payload block from a small-cap scan's results."""
    ranked = strat.rank_smallcap([r for r in survivors if r.get('factors')])
    rows = [{
        'ticker': r['ticker'], 'name': r.get('name'), 'sector': r.get('sector'),
        'mcap': r.get('mcap'), 'price': round(r['price'], 2) if r.get('price') else None,
        'composite': round(r['composite'], 2) if r.get('composite') is not None else None,
        'z': {k: (round(v, 2) if v is not None else None) for k, v in (r.get('z') or {}).items()},
        'trend': (r.get('trend') or {}).get('signal'),
    } for r in ranked]
    return {
        'rank': rows, 'n_universe': len(SMALLCAP_UNIVERSE),
        'n_passed': len(survivors), 'n_dropped': len(dropped), 'n_failed': len(failed),
        'dropped': [{'ticker': r['ticker'], 'reasons': r['reasons'], 'mcap': r.get('mcap')}
                    for r in dropped][:60],
        'weights': strat.SMALLCAP_WEIGHTS, 'params': strat.SMALLCAP_PARAMS,
    }


def _smallcap_only():
    """Run ONLY the small-cap pass and write its block to SC_BLOCK. Invoked as a *fresh subprocess*
    (see _run_smallcap_subprocess): Yahoo's quoteSummary/.info endpoint — which the quality gate needs —
    gets crumb-poisoned after the main run's ~300+ fundamental fetches, and new threads/sessions don't
    reset it within a process. A clean process gets a clean crumb, so the gate actually sees the data."""
    surv, drop, failed = screen_smallcap(SMALLCAP_UNIVERSE)
    block = _build_smallcap_block(surv, drop, failed)
    os.makedirs(os.path.dirname(SC_BLOCK), exist_ok=True)
    with open(SC_BLOCK, 'w', encoding='utf-8') as f:
        json.dump(block, f, indent=2, default=str)
    print(f"SMALLCAP_DONE passed={len(surv)} dropped={len(drop)} failed={len(failed)} "
          f"of {len(SMALLCAP_UNIVERSE)}", flush=True)
    return block


def _empty_smallcap_block():
    return {'rank': [], 'n_universe': len(SMALLCAP_UNIVERSE), 'n_passed': 0, 'n_dropped': 0,
            'n_failed': len(SMALLCAP_UNIVERSE), 'dropped': [],
            'weights': strat.SMALLCAP_WEIGHTS, 'params': strat.SMALLCAP_PARAMS}


def _spawn_smallcap():
    """Spawn a fresh Python process for the small-cap pass and read back its block (empty on error)."""
    import subprocess
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--smallcap-only'],
                              capture_output=True, text=True, timeout=600)
        for line in (proc.stdout or '').splitlines():
            if line.startswith('SMALLCAP_DONE'):
                print('  small-cap (fresh subprocess): ' + line.replace('SMALLCAP_DONE ', ''), flush=True)
        with open(SC_BLOCK, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  small-cap subprocess failed ({e.__class__.__name__}); empty block", flush=True)
        return _empty_smallcap_block()


def _is_rate_limited(block):
    """True if the block looks like a total Yahoo rate-limit wipe-out (nothing fetched)."""
    return block.get('n_passed', 0) == 0 and block.get('n_failed', 0) >= max(1, block.get('n_universe', 1))


def _run_smallcap_subprocess(initial_cooldown=300, retry_cooldown=300):
    """Run the small-cap pass in a fresh process. A clean crumb isn't enough on its own: Yahoo throttles
    crumb ACQUISITION per-IP after the main run's ~330 fundamental fetches, so a child spawned at a 0s gap
    still 401s. A cooldown lets that throttle lapse (a ~2min gap empirically clears it; we use more). Cools
    down first, then spawns; if it still gets fully rate-limited, cools longer and retries once. Worst case
    this just adds idle minutes to a background nightly — never aborts it."""
    if initial_cooldown:
        print(f"  cooling down {initial_cooldown}s so Yahoo's crumb endpoint un-throttles…", flush=True)
        time.sleep(initial_cooldown)
    block = _spawn_smallcap()
    if _is_rate_limited(block) and retry_cooldown:
        print(f"  small-cap still rate-limited; cooling {retry_cooldown}s and retrying once…", flush=True)
        time.sleep(retry_cooldown)
        block = _spawn_smallcap()
    return block


def main():
    t0 = time.time()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] screening {len(WATCHLIST)} tickers…", flush=True)
    # Gentle concurrency + a per-thread session keep Yahoo from issuing 'Invalid Crumb' 401s.
    rows, skipped = _scan(WATCHLIST, workers=5)
    print(f"  first pass: {len(rows)} ok, {len(skipped)} skipped ({time.time() - t0:.0f}s)", flush=True)
    if skipped:
        time.sleep(5)
        retry_rows, skipped = _scan(skipped, workers=3)
        rows.extend(retry_rows)
        print(f"  retry pass: +{len(retry_rows)} ok, {len(skipped)} still skipped", flush=True)

    print(f"  scanning {len(sct.ALL_SECTORS)} sectors + industries for oversold/rebound setups…", flush=True)
    sector_data = screen_sectors()

    # Options pass (US-optionable names): income/LEAPS candidates + accumulate ATM-IV history.
    print(f"  scanning options on {len(US_OPTIONABLE)} US names…", flush=True)
    iv_hist = _load_json(IVH, {})
    today_str = datetime.now().strftime('%Y-%m-%d')
    opt_rows = screen_options(US_OPTIONABLE, iv_hist)
    for r in opt_rows:
        iv_hist = opt.update_iv_history(iv_hist, r['ticker'], today_str, r.get('atm_iv'))

    def _ok_earnings(r):
        d = r.get('earnings_in_days')
        return not (d is not None and 0 <= d <= 45)
    ideas = sorted([r for r in opt_rows if r.get('premium_rich') and r.get('csp') and _ok_earnings(r)],
                   key=lambda r: (r['csp'].get('ann_yield_pct') or 0), reverse=True)
    print(f"  options: {len(opt_rows)} scanned, {len(ideas)} income ideas", flush=True)

    # Tracked open positions: live-quote each + compute management alerts.
    positions = posn.load(POS)
    pos_rows = screen_positions(positions)
    pos_rows.sort(key=lambda r: -r['actionable'])
    print(f"  positions: {len(positions)} tracked, "
          f"{sum(1 for r in pos_rows if r['actionable'])} need action", flush=True)

    # Multi-factor ranking + trend / market regime (systematic-strategy signals).
    ranked = strat.rank_universe([r for r in rows if r.get('factors')])
    factor_rows = [{
        'ticker': r['ticker'], 'name': r.get('name'), 'sector': r.get('sector'), 'price': r.get('price'),
        'composite': round(r['composite'], 2) if r.get('composite') is not None else None,
        'z': {k: (round(v, 2) if v is not None else None) for k, v in (r.get('z') or {}).items()},
        'trend': (r.get('trend') or {}).get('signal'),
    } for r in ranked]
    regime = strat.regime_gauge([r.get('trend') for r in rows if r.get('trend')])
    trends = {}
    for sym, nm in (('SPY', 'S&P 500'), ('DBMF', 'Managed futures (DBMF)'),
                    ('KMLM', 'Managed futures (KMLM)'), ('IEF', 'US 10y Treasuries')):
        try:
            h = _yf_ticker(sym).history(period='1y')
            cl = [float(x) for x in h['Close'].dropna().tolist()] if h is not None and not h.empty else []
            t = strat.trend_signal(cl)
            trends[sym] = {'name': nm, 'signal': t['signal'],
                           'pct_vs_sma': round(t['pct_vs_sma'], 1) if t['pct_vs_sma'] is not None else None}
        except Exception:
            pass
    print(f"  strategy: ranked {len(factor_rows)} names; "
          f"regime {regime.get('pct_up')}% above 200d", flush=True)

    # Small-cap quality-value sleeve: gate out junk/micro-caps, then rank survivors (value+quality tilt).
    # Run in a FRESH subprocess so the .info/quoteSummary endpoint (rate-limited late in this run) is clean.
    print(f"  scanning {len(SMALLCAP_UNIVERSE)} small-cap candidates (quality-value sleeve, fresh process)…", flush=True)
    smallcap_block = _run_smallcap_subprocess()

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'generated_human': datetime.now().strftime('%d %b %Y, %H:%M'),
        'universe': len(WATCHLIST), 'analysed': len(rows),
        'skipped': skipped, 'results': rows,
        'sectors': sector_data,
        'options': {'analysed': len(opt_rows), 'ideas': ideas[:40]},
        'position_alerts': pos_rows,
        'strategy': {'factor_rank': factor_rows[:50], 'regime': regime, 'trends': trends,
                     'weights': strat.DEFAULT_FACTOR_WEIGHTS},
        'smallcap': smallcap_block,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, default=str)
    with open(IVH, 'w', encoding='utf-8') as f:
        json.dump(iv_hist, f, indent=2, default=str)
    print(f"[{datetime.now():%H:%M:%S}] done in {time.time() - t0:.0f}s · "
          f"{len(rows)} analysed, {len(skipped)} skipped -> {OUT}", flush=True)


if __name__ == '__main__':
    if '--smallcap-only' in sys.argv:
        _smallcap_only()
    else:
        main()
