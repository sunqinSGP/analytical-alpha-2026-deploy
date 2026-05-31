"""
High Conviction Stock Screener — 2026 Framework
Scans a curated watchlist and assigns each stock a single best tier using the SAME
rubric as the Streamlit app (stock_analyzer.assign_screen_tier):
  - PLATINUM: Moat >= 6, Risk <= 1, moat COMPOUNDING, growth signal
  - GOLD:     Moat >= 5, Risk <= 2, growth signal
  - SILVER:   Moat >= 4, Risk <= 4, Circumvention Delta >= 4
where a "growth signal" = revenue-retention proxy >= 120% OR a bullish Forward-R40
inflection. (Retention is a total-revenue proxy, not true cohort NRR.)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stock_analyzer.alpha_engine import alpha_analysis, assign_screen_tier
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ===========================================================================
# CURATED WATCHLIST — ~120 stocks across all sectors & markets
# ===========================================================================
from stock_analyzer.universe import WATCHLIST  # single source of truth (edit there)

# ===========================================================================
# SCREENING LOGIC
# ===========================================================================

def screen_stock(ticker):
    """Run alpha analysis and return screening results."""
    try:
        r = alpha_analysis(ticker)
        if 'error' in r:
            return {'ticker': ticker, 'error': r['error']}

        moat = r['qualitative']['moat']
        risk = r['risk_management']['risk_factors']
        quant = r['quantitative']
        fwd = quant['forward_rule_of_40']
        nrr = quant['net_revenue_retention']
        nob = r['nob']
        perf = r['qualitative']['moat_performance']
        thesis = r['thesis']

        return {
            'ticker': ticker,
            'name': r['data']['name'],
            'nob': nob['name'],
            'moat_rating': moat['moat_rating'],
            'moat_label': moat['moat_label'],
            'circumvention_delta': moat.get('circumvention_delta', 0),
            'moat_performance': perf['performance'],
            'risk_score': risk['risk_score'],
            'risk_level': risk['risk_level'],
            'nrr_pct': nrr.get('estimated_nrr_pct'),
            'nrr_installed_growth': nrr.get('estimated_nrr_pct', 0) is not None and nrr['estimated_nrr_pct'] >= 120,
            'fwd_r40': fwd.get('forward_rule_40'),
            'trailing_r40': fwd.get('trailing_rule_40'),
            'fwd_inflection': fwd.get('inflection_signal', ''),
            'conviction': thesis['conviction'],
            'thesis_short': thesis['thesis'][:120],
            'price': r['data']['price'],
            'market_cap': r['data']['info'].get('marketCap'),
            'sector': r['data']['sector'],
            'industry': r['data']['industry'],
            'error': None,
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    print("=" * 90)
    print("  HIGH CONVICTION STOCK SCREENER — 2026 Strategic Growth Framework")
    print(f"  Scanning {len(WATCHLIST)} stocks across US, SGX, HKEX, EU markets")
    print("=" * 90)
    print()

    results = []
    errors = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(screen_stock, t): t for t in WATCHLIST}
        for i, future in enumerate(as_completed(futures)):
            ticker = futures[future]
            result = future.result()
            if result.get('error'):
                errors.append(result)
            else:
                results.append(result)
            elapsed = time.time() - start
            print(f"\r  [{i+1}/{len(WATCHLIST)}] Scanned {ticker:<10} | {i+1-len(errors)} passed | {len(errors)} errors | {elapsed:.0f}s", end='', flush=True)

    print("\n")

    if not results:
        print("No results. Check network connection.")
        return

    df = pd.DataFrame(results)

    # Single source of truth — same rubric as the Streamlit app (assign_screen_tier).
    # Each stock lands in exactly one (best) tier.
    df['tier'] = df.apply(lambda r: assign_screen_tier(
        r['moat_rating'], r['risk_score'], r['moat_performance'],
        r['nrr_pct'], r['fwd_inflection'], r['circumvention_delta']), axis=1)
    platinum = df[df['tier'] == 'PLATINUM'].sort_values('moat_rating', ascending=False)
    high_conviction = df[df['tier'] == 'GOLD'].sort_values('moat_rating', ascending=False)
    moderate_conviction = df[df['tier'] == 'SILVER'].sort_values('moat_rating', ascending=False)

    # ---- DISPLAY ----
    display_cols = ['ticker', 'name', 'nob', 'moat_rating', 'circumvention_delta',
                    'moat_performance', 'risk_score', 'nrr_pct', 'fwd_inflection',
                    'price', 'sector']

    def format_display(subset, label, criteria):
        print("=" * 100)
        print(f"  {label} — {len(subset)} stocks found")
        print(f"  Criteria: {criteria}")
        print("=" * 100)
        print()
        if len(subset) > 0:
            disp = subset[display_cols].copy()
            disp['price'] = disp['price'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else 'N/A')
            disp['nrr_pct'] = disp['nrr_pct'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else 'N/A')
            disp['moat_rating'] = disp['moat_rating'].apply(lambda x: f"{x:.1f}/10")
            disp.columns = ['Ticker', 'Name', 'NoB', 'Moat', 'Circ.Delta', 'Trend', 'Risk', 'NRR', 'Fwd R40', 'Price', 'Sector']
            print(disp.to_string(index=False))
        else:
            print("  No stocks in this tier.")
        print()

    format_display(platinum, 'PLATINUM — Highest Quality',
                   'Moat >= 6 | Risk <= 1 | Moat COMPOUNDING | NRR >= 120% or Fwd R40 Inflection')
    format_display(high_conviction, 'GOLD — High Conviction',
                   'Moat >= 5 | Risk <= 2 | NRR >= 120% or Fwd R40 Inflection')
    format_display(moderate_conviction, 'SILVER — Moderate Conviction',
                   'Moat >= 4 | Risk <= 4 | Circumvention Delta >= 4')

    # ---- SUMMARY STATS ----
    print()
    print("=" * 100)
    print(f"  SCREENING SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)
    print(f"  Total scanned:     {len(WATCHLIST)}")
    print(f"  Successful:        {len(results)}")
    print(f"  Errors:            {len(errors)}")
    print(f"  PLATINUM:          {len(platinum)}  (Moat>=6, Risk<=1, Compounding, Growth signal)")
    print(f"  GOLD:              {len(high_conviction)}  (Moat>=5, Risk<=2, Growth signal)")
    print(f"  SILVER:            {len(moderate_conviction)}  (Moat>=4, Risk<=4, Circ.Delta>=4)")
    print(f"  Time elapsed:      {time.time() - start:.0f}s")
    print()

    # Conviction distribution
    print("  Conviction Distribution:")
    for level in ['HIGH CONVICTION', 'MODERATE CONVICTION', 'SELECTIVE', 'OPPORTUNISTIC', 'PASS']:
        count = len(df[df['conviction'] == level])
        bar = '#' * (count // 2) if count > 0 else ''
        print(f"    {level:<22} {count:>3}  {bar}")

    # Moat distribution
    print()
    print("  Moat Rating Distribution:")
    for lo, hi, label in [(0, 3, 'No Moat (0-3)'), (3, 5, 'Narrow (3-5)'), (5, 7, 'Moderate (5-7)'), (7, 11, 'Wide (7-10)')]:
        count = len(df[(df['moat_rating'] >= lo) & (df['moat_rating'] < hi)])
        bar = '#' * (count // 2) if count > 0 else ''
        print(f"    {label:<22} {count:>3}  {bar}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    {e['ticker']}: {e['error']}")
        if len(errors) > 10:
            print(f"    ... and {len(errors)-10} more")


if __name__ == '__main__':
    main()
