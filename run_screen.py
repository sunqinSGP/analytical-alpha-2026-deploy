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
from stock_analyzer.alpha_engine import alpha_analysis, assign_screen_tier
from stock_analyzer.universe import WATCHLIST

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'screen_results.json')


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

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'generated_human': datetime.now().strftime('%d %b %Y, %H:%M'),
        'universe': len(WATCHLIST), 'analysed': len(rows),
        'skipped': skipped, 'results': rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"[{datetime.now():%H:%M:%S}] done in {time.time() - t0:.0f}s · "
          f"{len(rows)} analysed, {len(skipped)} skipped -> {OUT}", flush=True)


if __name__ == '__main__':
    main()
