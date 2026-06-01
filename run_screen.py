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
from stock_analyzer.universe import WATCHLIST
from stock_analyzer import sectors as sct
from stock_analyzer import options as opt
from stock_analyzer import positions as posn

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'screen_results.json')
IVH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'iv_history.json')
POS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'options_positions.json')
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
        return {
            'ticker': tk, 'name': r['data']['name'], 'nob': r['nob']['name'],
            'moat': round(moat['moat_rating'], 1), 'circ_delta': moat.get('circumvention_delta', 0),
            'moat_trend': r['qualitative']['moat_performance']['performance'],
            'risk': rf['risk_score'], 'risk_level': rf['risk_level'],
            'nrr': round(nrr) if nrr is not None else None, 'fwd_inflection': infl,
            'conviction': r['thesis']['conviction'], 'price': r['data']['price'],
            'sector': r['data']['sector'], 'tier': tier,
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

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'generated_human': datetime.now().strftime('%d %b %Y, %H:%M'),
        'universe': len(WATCHLIST), 'analysed': len(rows),
        'skipped': skipped, 'results': rows,
        'sectors': sector_data,
        'options': {'analysed': len(opt_rows), 'ideas': ideas[:40]},
        'position_alerts': pos_rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, default=str)
    with open(IVH, 'w', encoding='utf-8') as f:
        json.dump(iv_hist, f, indent=2, default=str)
    print(f"[{datetime.now():%H:%M:%S}] done in {time.time() - t0:.0f}s · "
          f"{len(rows)} analysed, {len(skipped)} skipped -> {OUT}", flush=True)


if __name__ == '__main__':
    main()
