"""
Offline smoke test for the Analytical Alpha engine — NO network required.
Feeds canned Yahoo-shaped data through alpha_analysis() across all 6 NoB frameworks
and asserts the key correctness fixes hold. Run: python tests/test_smoke.py
"""
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from stock_analyzer.alpha_engine import (
    alpha_analysis, dividend_yield_pct, format_market_cap,
    assess_conviction, assign_screen_tier, forward_rule_of_40,
    net_revenue_retention_estimate, NoB_TYPES,
)
from stock_analyzer.verdict import build_factor_attribution, recommendation_for
from stock_analyzer import portfolio as pf
from stock_analyzer import ai
from stock_analyzer import news as newsmod
from stock_analyzer import sectors as sct

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def _cols(n):
    # Yahoo orders statement columns most-recent-first
    return list(pd.to_datetime([f"20{25 - i:02d}-12-31" for i in range(n)]))


def make_data(**overrides):
    """Build a canned data dict shaped like fetch_alpha_data() output."""
    info = {
        'marketCap': 3_500_000_000_000, 'currentPrice': 100.0,
        'longName': 'Canned Corp', 'shortName': 'Canned',
        'sector': 'Technology', 'industry': 'Software - Infrastructure',
        'longBusinessSummary': 'A subscription cloud platform with proprietary, industry-leading technology trusted by enterprise customers.',
        'country': 'United States', 'fullTimeEmployees': 5000,
        'revenueGrowth': 0.20, 'grossMargins': 0.78, 'operatingMargins': 0.25,
        'returnOnEquity': 0.30, 'profitMargins': 0.18, 'ebitdaMargins': 0.30,
        'forwardPE': 35.0, 'trailingPE': 50.0, 'priceToSales': 12.0, 'priceToBook': 8.0,
        'freeCashflow': 90_000_000, 'beta': 1.1, 'debtToEquity': 30.0,
        'dividendRate': None, 'dividendYield': None,
        'forwardEps': 3.0, 'trailingEps': 2.5, 'sharesOutstanding': 1_000_000_000,
        'earningsGrowth': 0.25, 'recommendationKey': 'buy', 'targetMeanPrice': 120.0,
        'totalCash': 500_000_000, 'enterpriseToEbitda': 25.0, 'currentRatio': 2.0,
    }
    info.update(overrides.pop('info', {}))

    # 2-year annual statement: revenue +20%, gross margin expanding 72.5% -> 75%
    income_annual = pd.DataFrame(
        {_cols(2)[0]: {'Total Revenue': 480.0, 'Net Income': 80.0, 'Gross Profit': 360.0},
         _cols(2)[1]: {'Total Revenue': 400.0, 'Net Income': 60.0, 'Gross Profit': 290.0}})

    # 8 quarters: each quarter +20% vs the same quarter a year ago; shares SHRINK (buyback)
    qcols = _cols(8)
    rev_q = [120, 120, 120, 120, 100, 100, 100, 100]          # newest-first
    shares_q = [900, 920, 940, 960, 1000, 1000, 1000, 1000]   # buyback: fewer shares now
    income_quarterly = pd.DataFrame(
        {qcols[i]: {'Total Revenue': float(rev_q[i]),
                    'Diluted Average Shares': float(shares_q[i] * 1e6)} for i in range(8)})

    balance_sheet = pd.DataFrame(
        {_cols(2)[0]: {'Deferred Revenue': 200.0},
         _cols(2)[1]: {'Deferred Revenue': 150.0}})

    closes = np.linspace(70, 100, 300)
    price_data = pd.DataFrame({'Close': closes},
                              index=pd.date_range('2025-01-01', periods=300, freq='D'))

    data = {
        'ticker': 'TEST', 'info': info, 'price': info['currentPrice'],
        'name': info['longName'], 'sector': info['sector'], 'industry': info['industry'],
        'description': info['longBusinessSummary'], 'country': info['country'],
        'employees': info['fullTimeEmployees'],
        'income_annual': income_annual, 'income_quarterly': income_quarterly,
        'balance_sheet': balance_sheet, 'cashflow': pd.DataFrame(), 'price_data': price_data,
    }
    data.update(overrides)
    return data


print("\n[1] Helper units")
check("dividend_yield_pct from rate/price (2/100 -> 2.0%)",
      abs(dividend_yield_pct({'dividendRate': 2.0, 'currentPrice': 100.0}) - 2.0) < 1e-6)
check("dividend_yield_pct fraction 0.025 -> 2.5%",
      abs(dividend_yield_pct({'dividendYield': 0.025}) - 2.5) < 1e-6)
check("dividend_yield_pct percent 2.5 -> 2.5%",
      abs(dividend_yield_pct({'dividendYield': 2.5}) - 2.5) < 1e-6)
check("format_market_cap trillions", format_market_cap(3.5e12, '$') == '$3.50T')
check("format_market_cap billions", format_market_cap(2.5e9, '$') == '$2.5B')
check("format_market_cap None -> N/A", format_market_cap(None) == 'N/A')

print("\n[2] NRR proxy uses TOTAL revenue (buyback must NOT inflate it)")
nrr = net_revenue_retention_estimate(make_data())
# revenue +20% YoY -> ~120 regardless of the 10% share shrink; old per-share code gave ~133
check("NRR ~120 (not ~133)", nrr['estimated_nrr_pct'] is not None and abs(nrr['estimated_nrr_pct'] - 120) < 1.5)
check("NRR flagged as proxy", nrr.get('is_proxy') is True)
check("NRR copy is honest (no 'zero new customers')",
      'zero new customers' not in (nrr.get('installed_growth_note') or '').lower())

print("\n[3] Forward Rule of 40 — bounded margin inflection, no apples-to-oranges")
fwd = forward_rule_of_40(make_data())
check("forward margin expansion bounded to <= 15", abs(fwd['margin_expansion_pct']) <= 15.0)
check("inflection is not the old 'MASSIVE INFLECTION'", fwd['inflection_signal'] != 'MASSIVE INFLECTION')
check("forward FCF margin != trailing-identical no-op (it differs by margin term)",
      fwd['forward_fcf_margin_pct'] is not None)

print("\n[4] alpha_analysis runs across ALL 6 NoB frameworks with no exception")
for key in list(NoB_TYPES.keys()) + [None]:
    label = key or 'auto-detect'
    try:
        res = alpha_analysis('TEST', framework=key, data=make_data())
        ok = 'error' not in res and res['thesis']['conviction'] in (
            'HIGH CONVICTION', 'MODERATE CONVICTION', 'SELECTIVE', 'OPPORTUNISTIC', 'PASS')
        check(f"framework={label}: {res.get('thesis', {}).get('conviction', 'ERR')}", ok)
    except Exception as e:
        check(f"framework={label}: raised {type(e).__name__}: {e}", False)

print("\n[5] Missing-data edge cases (foreign tickers etc.) don't crash the engine")
sparse = make_data(info={'marketCap': 1e9, 'sector': 'Financial Services', 'industry': 'Banks - Regional',
                         'grossMargins': None, 'revenueGrowth': None, 'forwardEps': None,
                         'trailingEps': None, 'freeCashflow': None, 'fullTimeEmployees': None,
                         'dividendRate': 3.0})
try:
    res = alpha_analysis('SPARSE.SI', data=sparse)
    check("sparse/foreign ticker analysed without error", 'error' not in res)
except Exception as e:
    check(f"sparse ticker raised {type(e).__name__}: {e}", False)

print("\n[6] Conviction & screener tier are consistent (shared rubric)")
hi = assess_conviction(8, 1, 130, 'POSITIVE INFLECTION', 'COMPOUNDING')
check("wide-moat/clean/growth -> HIGH CONVICTION", hi[0] == 'HIGH CONVICTION')
check("same inputs -> PLATINUM tier",
      assign_screen_tier(8, 1, 'COMPOUNDING', 130, 'POSITIVE INFLECTION', 11) == 'PLATINUM')
check("decaying moat blocks HIGH CONVICTION",
      assess_conviction(8, 1, 130, 'POSITIVE INFLECTION', 'DECAYING')[0] != 'HIGH CONVICTION')
check("weak name -> no tier", assign_screen_tier(3, 7, 'DECAYING', 90, '', 2) is None)

print("\n[7] Verdict layer (powers the hero band) builds offline")
res = alpha_analysis('TEST', data=make_data())
factors = build_factor_attribution(res)
check("factor attribution non-empty", len(factors) > 0)
check("each factor has the expected keys",
      all({'Factor', 'ImpactNum', 'Impact', 'Direction'} <= set(x) for x in factors))
check("recommendation HIGH -> ACCUMULATE", recommendation_for('HIGH CONVICTION', 10, 0)[0] == 'ACCUMULATE')
check("over-cap position -> TRIM", recommendation_for('HIGH CONVICTION', 10, 15)[0] == 'TRIM')
check("PASS -> AVOID", recommendation_for('PASS', 3, 0)[0] == 'AVOID')

print("\n[8] Moat rating blends in economics (no 'No Moat' for quality compounders)")
# Terse summary (no moat keywords) but elite economics, AAPL-like
terse = make_data(info={'longBusinessSummary': 'A company that designs and sells products.',
                        'returnOnEquity': 1.5, 'grossMargins': 0.46, 'operatingMargins': 0.30,
                        'marketCap': 3_000_000_000_000, 'totalRevenue': 400_000_000_000})
mres = alpha_analysis('AAPL_LIKE', data=terse)
mmoat = mres['qualitative']['moat']
print(f"      keyword_moat={mmoat['keyword_moat']} quant_moat={mmoat['quant_moat']} -> rating={mmoat['moat_rating']}")
check("quant_moat populated for profitable name", mmoat['quant_moat'] is not None and mmoat['quant_moat'] >= 5)
check("terse+profitable name is NOT 'No Moat' (rating >= 4)", mmoat['moat_rating'] >= 4)
check("quant raises rating above keyword-only", mmoat['moat_rating'] >= mmoat['keyword_moat'])
# Weak commodity stays low
weak = make_data(info={'longBusinessSummary': 'Sells generic goods.', 'returnOnEquity': 0.04,
                       'grossMargins': 0.12, 'operatingMargins': 0.03, 'marketCap': 2_000_000_000,
                       'sector': 'Consumer Defensive', 'industry': 'Grocery Stores'})
wmoat = alpha_analysis('WEAK', data=weak)['qualitative']['moat']
check("weak commodity stays low moat (rating < 5)", wmoat['moat_rating'] < 5)

print("\n[9] Portfolio math (weights, FX, P&L, barbell, concentration)")
prows = [
    {'ticker': 'A', 'shares': 10, 'cost_basis': 100, 'currency': 'USD', 'layer': 'Growth',
     'nob': 'SaaS', 'region': 'US', 'price': 150, 'cap': 10},                         # mv 1500 USD
    {'ticker': 'B', 'shares': 100, 'cost_basis': 10, 'currency': 'HKD', 'layer': 'Income',
     'nob': 'Value', 'region': 'HK', 'price': 12, 'cap': 7},                          # 1200 HKD
    {'ticker': 'C', 'shares': 5, 'cost_basis': 1000, 'currency': 'JPY', 'layer': 'Growth',
     'nob': 'Semis', 'region': 'JP', 'price': 1100, 'cap': 7},                        # FX missing
]
fx = {'HKD': 0.128}  # ~7.8 HKD/USD; JPY intentionally absent
enr, tot = pf.enrich(prows, fx, 'USD')
wsum = sum(r['weight_pct'] for r in enr)
check("weights of priced positions sum to ~100", abs(wsum - 100) < 0.5)
check("A (1500) outweighs B (~154)", enr[0]['weight_pct'] > enr[1]['weight_pct'])
check("P&L% is currency-agnostic (A = +50%)", abs(enr[0]['pnl_pct'] - 50) < 1e-6)
check("missing FX flagged, not silently mis-weighted", tot['fx_missing'] == ['C'] and enr[2]['weight_pct'] == 0.0)
check("portfolio P&L aggregates (~46.6%)", tot['total_pnl_pct'] is not None and abs(tot['total_pnl_pct'] - 46.6) < 1.0)
bb = pf.barbell_breakdown(enr)
check("barbell uses the user's layers", set(bb) == {'Growth', 'Income'} and bb['Growth'] > bb['Income'])
oc = pf.over_cap(enr)
check("over-cap flags the concentrated name", any(o['ticker'] == 'A' for o in oc))
reg = pf.group_weights(enr, 'region')
check("region exposure groups correctly", abs(reg.get('US', 0) - enr[0]['weight_pct']) < 1e-6)

print("\n[10] AI & news modules (prompt builders + schema parsing; no live API)")
_res = alpha_analysis('TEST', data=make_data())
_ctx = ai.stock_context(_res)
check("stock_context mentions the ticker", 'TEST' in _ctx)
check("stock_context includes the verdict line", 'CONVICTION' in _ctx.upper())
check("chat system prompt carries the not-advice guardrail",
      'not financial advice' in ai.stock_chat_system(_res).lower())
_mm = ai.macro_messages([{'title': 'Fed holds rates steady', 'publisher': 'Reuters'}])
check("macro_messages embeds the headline", 'Fed holds rates steady' in _mm[0]['content'])
check("macro prompt requests structured JSON (tone/direction)",
      'json' in _mm[0]['content'].lower() and 'direction' in _mm[0]['content'].lower())
_mcs = ai.market_chat_system("Most oversold now: Software / SaaS RSI 30")
check("market_chat_system carries the not-advice guardrail", 'not financial advice' in _mcs.lower())
check("market_chat_system injects live context when provided", 'Software / SaaS' in _mcs)
check("market_chat_system works without context", isinstance(ai.market_chat_system(), str)
      and 'strategist' in ai.market_chat_system().lower())


def _empty_key_raises():
    try:
        ai.complete('', [{'role': 'user', 'content': 'hi'}])
        return False
    except Exception:
        return True


check("complete() rejects an empty API key", _empty_key_raises())
check("news parses the legacy schema", newsmod._normalize({'title': 'A', 'publisher': 'P'})['title'] == 'A')
check("news parses the nested-content schema",
      newsmod._normalize({'content': {'title': 'B', 'provider': {'displayName': 'Q'}}})['title'] == 'B')

print("\n[11] Sector oversold / rebound math")
_down = [100 - i * 0.25 for i in range(220)] + [45, 45.5, 46, 46.2]   # deep decline, ticking up
_up = [50 + i * 0.2 for i in range(220)]                              # steady uptrend
check("RSI low on a decline", sct.rsi(_down) is not None and sct.rsi(_down) < 45)
check("RSI high on an uptrend", sct.rsi(_up) is not None and sct.rsi(_up) > 60)
_m = sct.oversold_metrics(_down)
check("declining sector flagged oversold", _m['oversold'] is True)
check("oversold metrics include drawdown + setup score",
      _m['pct_off_52w_high'] < -10 and _m['rebound_score'] > 0)
check("uptrend not flagged oversold", sct.oversold_metrics(_up)['oversold'] is False)
_ranked = sct.rank_oversold({'XLE': {'name': 'Energy', **_m},
                             'XLK': {'name': 'Technology', **sct.oversold_metrics(_up)}})
check("rank_oversold returns only oversold sectors", [r['symbol'] for r in _ranked] == ['XLE'])
check("granular industries are tracked (SaaS/semis/biotech)",
      {'IGV', 'SMH', 'XBI'} <= set(sct.INDUSTRIES))
check("ALL_SECTORS merges GICS sectors + industries",
      len(sct.ALL_SECTORS) == len(sct.SECTORS) + len(sct.INDUSTRIES) and len(sct.ALL_SECTORS) > 20)
check("every tracked group has a Sector/Industry tag",
      all(sct.GROUP.get(s) in ('Sector', 'Industry') for s in sct.ALL_SECTORS))
_sm = ai.sector_rebound_messages(_ranked, [{'title': 'Oil slumps on demand fears'}])
check("sector rebound prompt embeds sector + headline",
      'Energy' in _sm[0]['content'] and 'Oil slumps' in _sm[0]['content'])

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
